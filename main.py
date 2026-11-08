import difflib
import time
import mysql.connector
import pyttsx3
import speech_recognition as sr

USE_VOICE = True  # True = use the microphone, False = type instead

engine = pyttsx3.init()
engine.setProperty('rate', 160)   # speaking speed (lower = slower)

# Words that Google often hears wrongly -> the name used in our database.
# You can add more lines here if you find other mistakes.
station_fixes = {
    'dacca': 'dhaka',
    'daka': 'dhaka',
    'kulna': 'khulna',
    'culna': 'khulna',
    'rajsahi': 'rajshahi',
    'rajshai': 'rajshahi',
    'rajshahee': 'rajshahi',
}

# how the time is shown, for example 8:00 AM
time_style = '%l:%i %p'

numbers = {'one': 1, 'won': 1, 'first': 1,
           'two': 2, 'to': 2, 'too': 2, 'second': 2,
           'three': 3, 'third': 3, 'four': 4, 'for': 4,
           'five': 5, 'six': 6, 'seven': 7, 'eight': 8,
           'nine': 9, 'ten': 10}


# ---------- voice functions ----------

def speak(text):
    print('System:', text)
    engine.say(text)
    engine.runAndWait()
    time.sleep(0.3)   # small pause so the mic does not hear the speaker


def listen():
    # listens once. Returns the text, or '' if something went wrong
    if not USE_VOICE:
        return input('You: ').lower()

    r = sr.Recognizer()
    r.pause_threshold = 1.0   # wait 1 second of silence before stopping
    try:
        with sr.Microphone() as source:
            # stay quiet for this 1 second, the mic measures the room noise
            r.adjust_for_ambient_noise(source, duration=1)
            print('Listening... (speak now)')
            audio = r.listen(source, timeout=10, phrase_time_limit=10)
        # en-IN works better for South Asian accents
        text = r.recognize_google(audio, language='en-IN').lower()
        print('You said:', text)
        return text
    except sr.WaitTimeoutError:
        print('Error: you did not speak in time')
    except sr.UnknownValueError:
        print('Error: could not understand the audio')
    except sr.RequestError as e:
        print('Error: internet or Google service problem:', e)
    except Exception as e:
        print('Error: microphone problem:', e)
    return ''


def listen_retry():
    # tries 3 times by voice. If voice keeps failing, asks the user to type.
    for attempt in range(3):
        text = listen()
        if text != '':
            return text
        if attempt < 2:
            speak('Sorry, please say that again.')
    speak('I could not hear you. Please type it instead.')
    return input('You (type): ').lower()


# ---------- helper functions ----------

def get_number(text):
    # looks at each word and returns the first number found, or 0
    for word in text.split():
        if word.isdigit():
            return int(word)
        if word in numbers:
            return numbers[word]
    return 0


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


def search(cur, from_name, to_name):
    cur.execute('''
        SELECT Schedule.schedule_id, Transport.name, Transport.type,
               TIME_FORMAT(Schedule.departure_time, %s), Schedule.fare
        FROM Schedule
        JOIN Transport ON Schedule.transport_id = Transport.transport_id
        JOIN Station AS s1 ON Schedule.from_station = s1.station_id
        JOIN Station AS s2 ON Schedule.to_station = s2.station_id
        WHERE s1.name = %s AND s2.name = %s
        ORDER BY Schedule.departure_time
    ''', (time_style, from_name, to_name))
    return cur.fetchall()


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


# ---------- main features ----------

def enquiry(cur, conn):
    speak('Where do you want to go? For example, say Dhaka to Khulna.')
    text = listen_retry()
    stations = find_stations(text, cur)

    if len(stations) < 2:
        speak('Sorry, I did not understand the stations.')
        return

    speak(f'Searching from {stations[0]} to {stations[1]}.')
    results = search(cur, stations[0], stations[1])
    if len(results) == 0:
        speak('No transport found.')
        return

    for number, row in enumerate(results, start=1):
        schedule_id, name, kind, time_text, fare = row
        left = seats_left(cur, schedule_id)
        speak(f'Option {number}. {kind} {name} at {time_text}. Fare {fare} taka. '
              f'{left["window"]} window seats and {left["aisle"]} aisle seats left.')

    speak('Say the option number to book, or say no.')
    answer = listen_retry()
    picked = get_number(answer)
    if 'no' in answer.split() or picked == 0 or picked > len(results):
        speak('Okay, no booking.')
    else:
        book_ticket(cur, conn, results[picked - 1][0])


def book_ticket(cur, conn, schedule_id):
    left = seats_left(cur, schedule_id)
    if left['window'] + left['aisle'] == 0:
        speak('Sorry, no seats are available.')
        return

    speak('Say window or aisle for your seat.')
    answer = listen_retry()
    # Google sometimes hears 'aisle' as 'isle' or "i'll"
    if 'window' in answer:
        seat_type = 'window'
    elif 'aisle' in answer or 'isle' in answer or "i'll" in answer:
        seat_type = 'aisle'
    else:
        speak('Sorry, I did not understand the seat type.')
        return

    if left[seat_type] == 0:
        speak(f'Sorry, no {seat_type} seats are left.')
        return

    speak('Please say your name.')
    name = listen_retry().title()
    if name == '':
        speak('Sorry, I did not get your name.')
        return

    # take the first free seat of that type
    cur.execute('''
        SELECT seat_id, seat_number FROM Seat
        WHERE schedule_id = %s AND seat_type = %s AND is_booked = 0
        ORDER BY seat_number LIMIT 1
    ''', (schedule_id, seat_type))
    seat_id, seat_number = cur.fetchone()

    cur.execute('INSERT INTO Booking (seat_id, passenger_name) VALUES (%s, %s)',
                (seat_id, name))
    booking_id = cur.lastrowid
    cur.execute('UPDATE Seat SET is_booked = 1 WHERE seat_id = %s', (seat_id,))
    conn.commit()   # saves the booking and the seat change together
    speak(f'Ticket confirmed for {name}. {seat_type} seat number {seat_number}. '
          f'Your booking number is {booking_id}.')


def view_booking(cur):
    speak('Say your booking number.')
    booking_id = get_number(listen_retry())
    if booking_id == 0:
        speak('Sorry, I did not understand the number.')
        return

    cur.execute('''
        SELECT Booking.passenger_name, Transport.name,
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
        speak('No booking found.')
    else:
        name, transport, time_text, fare, seat_number, seat_type = row
        speak(f'{name}, you are booked on {transport} at {time_text}. '
              f'{seat_type} seat number {seat_number}. Fare is {fare} taka.')


def cancel_booking(cur, conn):
    speak('Say your booking number.')
    booking_id = get_number(listen_retry())
    if booking_id == 0:
        speak('Sorry, I did not understand the number.')
        return

    cur.execute('SELECT seat_id FROM Booking WHERE booking_id = %s', (booking_id,))
    row = cur.fetchone()
    if row is None:
        speak('No booking found.')
        return

    cur.execute('DELETE FROM Booking WHERE booking_id = %s', (booking_id,))
    cur.execute('UPDATE Seat SET is_booked = 0 WHERE seat_id = %s', (row[0],))
    conn.commit()
    speak('Your booking is cancelled.')


# ---------- main program ----------

conn = mysql.connector.connect(
    host='localhost',
    user='root',
    password='',          # XAMPP's default is an empty password
    database='voiceroute')
cur = conn.cursor(buffered=True)

# shows which stations are really inside the database
cur.execute('SELECT name FROM Station')
print('Stations in database:', [row[0] for row in cur.fetchall()])

speak('Welcome to VoiceRoute.')

while True:
    speak('Say enquiry, view, cancel, or stop.')
    command = listen_retry()

    if 'stop' in command or 'exit' in command or 'bye' in command:
        speak('Goodbye.')
        break
    elif 'enquiry' in command or 'inquiry' in command or 'query' in command or 'book' in command:
        enquiry(cur, conn)
    elif 'view' in command or 'check' in command or 'show' in command:
        view_booking(cur)
    elif 'cancel' in command or 'delete' in command:
        cancel_booking(cur, conn)
    else:
        speak('Sorry, I did not understand.')

conn.close()