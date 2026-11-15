import os
import mysql.connector

# On Render / online database: values come from Environment Variables.
# On your own computer (XAMPP): the second value (after the comma) is used.
host = os.environ.get('DB_HOST', 'localhost')
port = int(os.environ.get('DB_PORT', '3306'))
user = os.environ.get('DB_USER', 'root')
password = os.environ.get('DB_PASSWORD', '')
db_name = os.environ.get('DB_NAME', 'voiceroute')

if host == 'localhost':
    # XAMPP: connect first, then create the database
    conn = mysql.connector.connect(host=host, port=port, user=user, password=password)
    cur = conn.cursor()
    cur.execute('CREATE DATABASE IF NOT EXISTS ' + db_name)
    cur.execute('USE ' + db_name)
else:
    # online database: it already exists, so connect to it directly
    conn = mysql.connector.connect(host=host, port=port, user=user,
                                   password=password, database=db_name)
    cur = conn.cursor()

# delete old tables so this file can be run again to reset the data
cur.execute('DROP TABLE IF EXISTS Booking')
cur.execute('DROP TABLE IF EXISTS Seat')
cur.execute('DROP TABLE IF EXISTS Schedule')
cur.execute('DROP TABLE IF EXISTS Transport')
cur.execute('DROP TABLE IF EXISTS Station')

cur.execute('''CREATE TABLE Station (
    station_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE)''')

cur.execute('''CREATE TABLE Transport (
    transport_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    type VARCHAR(20) NOT NULL)''')

cur.execute('''CREATE TABLE Schedule (
    schedule_id INT AUTO_INCREMENT PRIMARY KEY,
    transport_id INT NOT NULL,
    from_station INT NOT NULL,
    to_station INT NOT NULL,
    departure_time TIME NOT NULL,
    fare INT NOT NULL CHECK (fare > 0),
    FOREIGN KEY (transport_id) REFERENCES Transport(transport_id),
    FOREIGN KEY (from_station) REFERENCES Station(station_id),
    FOREIGN KEY (to_station) REFERENCES Station(station_id))''')

# every schedule has its own seats. is_booked: 0 = free, 1 = booked
cur.execute('''CREATE TABLE Seat (
    seat_id INT AUTO_INCREMENT PRIMARY KEY,
    schedule_id INT NOT NULL,
    seat_number INT NOT NULL,
    seat_type VARCHAR(10) NOT NULL CHECK (seat_type IN ('window', 'aisle')),
    is_booked TINYINT NOT NULL DEFAULT 0,
    UNIQUE (schedule_id, seat_number),
    FOREIGN KEY (schedule_id) REFERENCES Schedule(schedule_id))''')

cur.execute('''CREATE TABLE Booking (
    booking_id INT AUTO_INCREMENT PRIMARY KEY,
    seat_id INT NOT NULL UNIQUE,
    passenger_name VARCHAR(50) NOT NULL,
    FOREIGN KEY (seat_id) REFERENCES Seat(seat_id))''')

# sample data (stations must be written in lowercase)
cur.execute('''INSERT INTO Station VALUES (1, 'dhaka'), (2, 'khulna'), (3, 'rajshahi')''')

cur.execute('''INSERT INTO Transport VALUES
    (1, 'Green Line', 'bus'),
    (2, 'Hanif Enterprise', 'bus'),
    (3, 'Sundarban Express', 'train'),
    (4, 'Silk City Express', 'train')''')

# station ids: 1 = dhaka, 2 = khulna, 3 = rajshahi
# each route is (transport_id, from_station, to_station, fare)
routes = [
    (1, 1, 2, 900),   # Green Line         dhaka -> khulna
    (3, 1, 2, 700),   # Sundarban Express  dhaka -> khulna
    (1, 2, 1, 900),   # Green Line         khulna -> dhaka
    (3, 2, 1, 700),   # Sundarban Express  khulna -> dhaka
    (2, 1, 3, 800),   # Hanif Enterprise   dhaka -> rajshahi
    (4, 1, 3, 600),   # Silk City Express  dhaka -> rajshahi
    (2, 3, 1, 800),   # Hanif Enterprise   rajshahi -> dhaka
    (4, 3, 1, 600),   # Silk City Express  rajshahi -> dhaka
]

# every transport runs 3 times a day (24 hour time)
times = {
    1: ['08:00:00', '13:00:00', '19:00:00'],   # Green Line
    2: ['09:00:00', '15:00:00', '21:00:00'],   # Hanif Enterprise
    3: ['07:00:00', '14:00:00', '21:30:00'],   # Sundarban Express
    4: ['06:30:00', '13:30:00', '20:00:00'],   # Silk City Express
}

for transport_id, from_station, to_station, fare in routes:
    for departure_time in times[transport_id]:
        cur.execute('''INSERT INTO Schedule
            (transport_id, from_station, to_station, departure_time, fare)
            VALUES (%s, %s, %s, %s, %s)''',
            (transport_id, from_station, to_station, departure_time, fare))
        schedule_id = cur.lastrowid

        # 20 seats for every trip: 10 window seats and 10 aisle seats
        for number in range(1, 21):
            if number % 4 == 0 or number % 4 == 1:
                seat_type = 'window'
            else:
                seat_type = 'aisle'
            cur.execute('INSERT INTO Seat (schedule_id, seat_number, seat_type) VALUES (%s, %s, %s)',
                        (schedule_id, number, seat_type))

conn.commit()
conn.close()
print('Database created.')
