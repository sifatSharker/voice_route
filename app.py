import difflib
import mysql.connector
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# how the time is shown, for example 8:00 AM
time_style = '%l:%i %p'

# Words that Google often hears wrongly -> the name used in our database.
station_fixes = {
    'dacca': 'dhaka',
    'daka': 'dhaka',
    'kulna': 'khulna',
    'culna': 'khulna',
    'rajsahi': 'rajshahi',
    'rajshai': 'rajshahi',
    'rajshahee': 'rajshahi',
}


# ---------- helper functions ----------

def get_db():
    # opens a new connection for every request
    return mysql.connector.connect(
        host='localhost',
        user='root',
        password='',          # XAMPP's default is an empty password
        database='voiceroute')


def find_stations(text, cur):
    # the station said first is 'from', the next is 'to'
    cur.execute('SELECT name FROM Station')
    names = [row[0] for row in cur.fetchall()]

    # fix common wrong spellings first
    for wrong, right in station_fixes.items():
        text = text.replace(wrong, right)

    found = []   # list of (position in sentence, station name)

    # step 1: exact match
    for name in names:
        position = text.find(name)
        if position != -1:
            found.append((position, name))

    # step 2: close match, so 'sylet' still finds 'sylhet'
    already = [name for position, name in found]
    for word in text.split():
        match = difflib.get_close_matches(word, names, n=1, cutoff=0.7)

        # step 3: the start of a name, so 'raj' finds 'rajshahi'
        if len(match) == 0 and len(word) >= 3:
            for name in names:
                if name.startswith(word):
                    match = [name]

        if len(match) > 0 and match[0] not in already:
            found.append((text.find(word), match[0]))
            already.append(match[0])

    found.sort()
    return [name for position, name in found]


def seats_left(cur, schedule_id):
    # GROUP BY counts the free seats of each type (window / aisle)
    cur.execute('''
        SELECT seat_type, COUNT(*)
        FROM Seat
        WHERE schedule_id = %s AND is_booked = 0
        GROUP BY seat_type
    ''', (schedule_id,))
    left = {'window': 0, 'aisle': 0}
    for seat_type, count in cur.fetchall():
        left[seat_type] = count
    return left


def get_booking(cur, booking_id):
    # returns the full details of one booking, or None
    cur.execute('''
        SELECT Booking.booking_id, Booking.passenger_name, Transport.name,
               TIME_FORMAT(Schedule.departure_time, %s),
               Schedule.fare, Seat.seat_number, Seat.seat_type
        FROM Booking
        JOIN Seat ON Booking.seat_id = Seat.seat_id
        JOIN Schedule ON Seat.schedule_id = Schedule.schedule_id
        JOIN Transport ON Schedule.transport_id = Transport.transport_id
        WHERE Booking.booking_id = %s
    ''', (time_style, booking_id))
    row = cur.fetchone()
    if row is None:
        return None
    return {
        'booking_id': row[0],
        'name': row[1],
        'transport': row[2],
        'time': row[3],
        'fare': row[4],
        'seat_number': row[5],
        'seat_type': row[6],
    }


# ---------- web pages and API ----------

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/api/search', methods=['POST'])
def api_search():
    text = request.get_json().get('text', '').lower()
    conn = get_db()
    cur = conn.cursor(buffered=True)

    stations = find_stations(text, cur)
    if len(stations) < 2:
        conn.close()
        return jsonify({'ok': False, 'message': 'Sorry, I did not understand the stations. Try saying Dhaka to Khulna.'})

    cur.execute('''
        SELECT Schedule.schedule_id, Transport.name, Transport.type,
               TIME_FORMAT(Schedule.departure_time, %s), Schedule.fare
        FROM Schedule
        JOIN Transport ON Schedule.transport_id = Transport.transport_id
        JOIN Station AS s1 ON Schedule.from_station = s1.station_id
        JOIN Station AS s2 ON Schedule.to_station = s2.station_id
        WHERE s1.name = %s AND s2.name = %s
        ORDER BY Schedule.departure_time
    ''', (time_style, stations[0], stations[1]))
    rows = cur.fetchall()

    results = []
    for schedule_id, name, kind, time_text, fare in rows:
        left = seats_left(cur, schedule_id)
        results.append({
            'schedule_id': schedule_id,
            'name': name,
            'type': kind,
            'time': time_text,
            'fare': fare,
            'window': left['window'],
            'aisle': left['aisle'],
        })

    conn.close()
    return jsonify({'ok': True, 'from': stations[0], 'to': stations[1], 'results': results})


@app.route('/api/book', methods=['POST'])
def api_book():
    data = request.get_json()
    schedule_id = data.get('schedule_id')
    seat_type = data.get('seat_type')
    name = data.get('name', '').strip().title()

    if seat_type not in ('window', 'aisle'):
        return jsonify({'ok': False, 'message': 'Please choose a window or aisle seat.'})
    if name == '':
        return jsonify({'ok': False, 'message': 'Please enter your name.'})

    conn = get_db()
    cur = conn.cursor(buffered=True)
    try:
        # take the first free seat of that type
        cur.execute('''
            SELECT seat_id FROM Seat
            WHERE schedule_id = %s AND seat_type = %s AND is_booked = 0
            ORDER BY seat_number LIMIT 1
        ''', (schedule_id, seat_type))
        row = cur.fetchone()
        if row is None:
            conn.close()
            return jsonify({'ok': False, 'message': f'Sorry, no {seat_type} seats are left.'})
        seat_id = row[0]

        cur.execute('INSERT INTO Booking (seat_id, passenger_name) VALUES (%s, %s)',
                    (seat_id, name))
        booking_id = cur.lastrowid
        cur.execute('UPDATE Seat SET is_booked = 1 WHERE seat_id = %s', (seat_id,))
        conn.commit()   # saves the booking and the seat change together
    except mysql.connector.Error as e:
        conn.rollback()   # if anything failed, undo both changes
        conn.close()
        return jsonify({'ok': False, 'message': 'Database error: ' + str(e)})

    booking = get_booking(cur, booking_id)
    conn.close()
    return jsonify({'ok': True, 'booking': booking})


@app.route('/api/view', methods=['POST'])
def api_view():
    booking_id = request.get_json().get('booking_id')
    conn = get_db()
    cur = conn.cursor(buffered=True)
    booking = get_booking(cur, booking_id)
    conn.close()

    if booking is None:
        return jsonify({'ok': False, 'message': 'No booking found.'})
    return jsonify({'ok': True, 'booking': booking})


@app.route('/api/cancel', methods=['POST'])
def api_cancel():
    booking_id = request.get_json().get('booking_id')
    conn = get_db()
    cur = conn.cursor(buffered=True)
    try:
        cur.execute('SELECT seat_id FROM Booking WHERE booking_id = %s', (booking_id,))
        row = cur.fetchone()
        if row is None:
            conn.close()
            return jsonify({'ok': False, 'message': 'No booking found.'})

        cur.execute('DELETE FROM Booking WHERE booking_id = %s', (booking_id,))
        cur.execute('UPDATE Seat SET is_booked = 0 WHERE seat_id = %s', (row[0],))
        conn.commit()
    except mysql.connector.Error as e:
        conn.rollback()
        conn.close()
        return jsonify({'ok': False, 'message': 'Database error: ' + str(e)})

    conn.close()
    return jsonify({'ok': True, 'message': 'Your booking is cancelled.'})


if __name__ == '__main__':
    app.run(debug=True)
