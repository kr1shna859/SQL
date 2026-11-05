import sqlite3
import random
from datetime import datetime, timedelta
from pathlib import Path


def build_schema(conn):
    """Create the tables, relationships and attribute constraints."""

    conn.executescript("""
    CREATE TABLE class_formats (
        format_id INTEGER PRIMARY KEY,
        format_name TEXT NOT NULL UNIQUE
            CHECK(length(trim(format_name)) > 0),
        intensity_level TEXT NOT NULL
            CHECK(intensity_level IN ('Low','Moderate','High')),
        standard_duration_minutes INTEGER NOT NULL
            CHECK(typeof(standard_duration_minutes) = 'integer'
                  AND standard_duration_minutes BETWEEN 20 AND 90),
        maximum_group_size INTEGER NOT NULL
            CHECK(typeof(maximum_group_size) = 'integer'
                  AND maximum_group_size BETWEEN 1 AND 20),
        standard_booking_fee REAL NOT NULL
            CHECK(standard_booking_fee > 0),
        required_equipment_type TEXT NOT NULL
            CHECK(required_equipment_type IN ('Mat','Cycle'))
    );

    CREATE TABLE studio_spaces (
        space_id INTEGER PRIMARY KEY,
        space_name TEXT NOT NULL UNIQUE,
        floor_area_m2 REAL NOT NULL CHECK(floor_area_m2 > 0),
        safe_capacity INTEGER NOT NULL
            CHECK(typeof(safe_capacity) = 'integer'
                  AND safe_capacity > 0),
        ventilation_type TEXT NOT NULL
            CHECK(ventilation_type IN ('Mechanical','Mixed'))
    );

    CREATE TABLE scheduled_classes (
        class_id INTEGER PRIMARY KEY,
        format_id INTEGER NOT NULL
            REFERENCES class_formats(format_id) ON DELETE RESTRICT,
        space_id INTEGER NOT NULL
            REFERENCES studio_spaces(space_id) ON DELETE RESTRICT,
        starts_at TEXT NOT NULL
            CHECK(datetime(starts_at) IS NOT NULL
                  AND starts_at = datetime(starts_at)),
        ends_at TEXT NOT NULL
            CHECK(datetime(ends_at) IS NOT NULL
                  AND ends_at = datetime(ends_at)),
        room_temperature_c REAL
            CHECK(room_temperature_c BETWEEN 10 AND 35),
        booking_fee REAL NOT NULL CHECK(booking_fee > 0),

        CHECK(ends_at > starts_at),
        UNIQUE(space_id, starts_at)
    );

    CREATE TABLE class_bookings (
        class_id INTEGER NOT NULL
            REFERENCES scheduled_classes(class_id) ON DELETE RESTRICT,
        booking_no INTEGER NOT NULL
            CHECK(typeof(booking_no) = 'integer' AND booking_no > 0),
        participant_code TEXT NOT NULL
            CHECK(length(trim(participant_code)) > 0),
        booked_at TEXT NOT NULL
            CHECK(datetime(booked_at) IS NOT NULL
                  AND booked_at = datetime(booked_at)),
        booking_status TEXT NOT NULL
            CHECK(booking_status IN ('Attended','No-show','Cancelled')),
        amount_paid REAL NOT NULL CHECK(amount_paid >= 0),
        feedback_score INTEGER
            CHECK(
                feedback_score IS NULL OR (
                    typeof(feedback_score) = 'integer'
                    AND feedback_score BETWEEN 1 AND 5
                )
            ),

        PRIMARY KEY(class_id, booking_no),
        CHECK(booking_status = 'Attended' OR feedback_score IS NULL),
        CHECK(booking_status != 'Cancelled' OR amount_paid = 0)
    );

    CREATE TABLE equipment_items (
        equipment_id INTEGER PRIMARY KEY,
        asset_code TEXT NOT NULL UNIQUE,
        space_id INTEGER NOT NULL
            REFERENCES studio_spaces(space_id) ON DELETE RESTRICT,
        equipment_type TEXT NOT NULL
            CHECK(equipment_type IN ('Mat','Cycle')),
        purchase_date TEXT NOT NULL
            CHECK(date(purchase_date) IS NOT NULL
                  AND purchase_date = date(purchase_date)),
        purchase_cost REAL NOT NULL CHECK(purchase_cost > 0),
        equipment_weight_kg REAL NOT NULL CHECK(equipment_weight_kg > 0)
    );

    CREATE TABLE equipment_checks (
        equipment_id INTEGER NOT NULL
            REFERENCES equipment_items(equipment_id) ON DELETE RESTRICT,
        check_no INTEGER NOT NULL
            CHECK(typeof(check_no) = 'integer' AND check_no > 0),
        class_id INTEGER NOT NULL
            REFERENCES scheduled_classes(class_id) ON DELETE RESTRICT,
        checked_at TEXT NOT NULL
            CHECK(datetime(checked_at) IS NOT NULL
                  AND checked_at = datetime(checked_at)),
        condition_grade TEXT NOT NULL
            CHECK(condition_grade IN ('Poor','Fair','Good','Excellent')),
        action_required TEXT NOT NULL
            CHECK(action_required IN ('None','Monitor','Remove')),
        notes TEXT,

        PRIMARY KEY(equipment_id, check_no),
        UNIQUE(equipment_id, class_id),
        CHECK(condition_grade != 'Poor' OR action_required = 'Remove')
    );

    CREATE INDEX booking_participant
        ON class_bookings(participant_code);

    CREATE INDEX check_class
        ON equipment_checks(class_id);
    """)


def create_catalogue(conn, rng):
    """Create fictional class offerings, studios and physical equipment."""

    # Nominal: class name, equipment type and ventilation type.
    # Ordinal: intensity Low < Moderate < High.
    # Ordinal: condition Poor < Fair < Good < Excellent.
    # Feedback scores are ordered categories: 1 < 2 < 3 < 4 < 5.
    # Interval: room temperature in Celsius.
    # Ratio: duration, floor area, equipment weight and costs.
    #
    # Prices are illustrative GBP amounts, not market estimates.

    offers = [
        ("Gentle mobility", "Low", 30, 9, "Mat"),
        ("Stretch and balance", "Low", 40, 10, "Mat"),
        ("Core foundations", "Moderate", 45, 12, "Mat"),
        ("Pilates practice", "Moderate", 50, 14, "Mat"),
        ("Floor conditioning", "High", 40, 13, "Mat"),
        ("Cycle introduction", "Low", 30, 10, "Cycle"),
        ("Steady cycling", "Moderate", 40, 12, "Cycle"),
        ("Cycle endurance", "Moderate", 55, 15, "Cycle"),
        ("Cycle intervals", "High", 35, 14, "Cycle"),
        ("Cycle challenge", "High", 45, 16, "Cycle")
    ]

    conn.executemany(
        "INSERT INTO class_formats VALUES (?,?,?,?,?,?,?)",
        [
            (i, name, level, minutes, 10, fee, kind)
            for i, (name, level, minutes, fee, kind)
            in enumerate(offers, 1)
        ]
    )

    conn.executemany(
        "INSERT INTO studio_spaces VALUES (?,?,?,?,?)",
        [
            (1, "Willow", 85, 12, "Mechanical"),
            (2, "Cedar", 95, 14, "Mixed"),
            (3, "Maple", 90, 12, "Mechanical"),
            (4, "Birch", 110, 16, "Mixed"),
            (5, "Elm", 100, 14, "Mechanical")
        ]
    )

    # Each studio has ten mats and ten stationary cycles.
    # The space link avoids allocating equipment from another room.
    equipment_pools = {}
    equipment_id = 0

    for space_id in range(1, 6):
        for kind in ["Mat", "Cycle"]:
            equipment_pools[space_id, kind] = []

            for _ in range(10):
                equipment_id += 1

                cost = (
                    rng.uniform(25, 65)
                    if kind == "Mat"
                    else rng.uniform(650, 1300)
                )

                weight = (
                    rng.uniform(0.8, 2.0)
                    if kind == "Mat"
                    else rng.uniform(35, 55)
                )

                purchase_date = (
                    f"2024-{rng.randint(1, 10):02d}-"
                    f"{rng.randint(1, 28):02d}"
                )

                conn.execute(
                    "INSERT INTO equipment_items VALUES (?,?,?,?,?,?,?)",
                    (
                        equipment_id,
                        f"EQ-{equipment_id:03d}",
                        space_id,
                        kind,
                        purchase_date,
                        round(cost, 2),
                        round(weight, 2)
                    )
                )

                equipment_pools[space_id, kind].append(equipment_id)

    return offers, equipment_pools


def fill_activity(conn, rng, offers, equipment_pools):
    """Generate classes, bookings and pre-class equipment checks."""

    bookings = []
    classes = []
    checks = []

    check_numbers = {i: 0 for i in range(1, 101)}

    # Fictional codes avoid collecting names or contact details.
    participants = [f"P-{i:04d}" for i in range(1, 301)]

    for day_index in range(220):
        # Five classes per day over 220 consecutive operating days.
        # One class is scheduled in each studio.
        available_people = participants.copy()

        for space_id in range(1, 6):
            class_id = day_index * 5 + space_id

            format_index = rng.choices(
                range(10),
                weights=[12, 10, 15, 14, 9, 10, 10, 8, 7, 5]
            )[0]

            name, intensity, minutes, fee, kind = offers[format_index]

            starts = datetime(2025, 1, 1, 10) + timedelta(days=day_index)
            ends = starts + timedelta(minutes=minutes)

            temperature = round(
                max(16, min(28, rng.gauss(21, 1.5))),
                1
            )

            classes.append([
                class_id,
                format_index + 1,
                space_id,
                starts.isoformat(" "),
                ends.isoformat(" "),
                temperature,
                float(fee)
            ])

            # Class sizes vary instead of always reaching capacity.
            booking_count = rng.choices(
                [6, 7, 8, 9, 10],
                weights=[8, 12, 25, 30, 25]
            )[0]

            selected_people = rng.sample(
                available_people,
                booking_count
            )

            # Avoid putting one participant into simultaneous classes.
            selected_set = set(selected_people)
            available_people = [
                person for person in available_people
                if person not in selected_set
            ]

            for booking_no, person in enumerate(selected_people, 1):
                status = rng.choices(
                    ["Attended", "No-show", "Cancelled"],
                    weights=[84, 8, 8]
                )[0]

                booked = starts - timedelta(
                    days=rng.randint(1, 14),
                    hours=rng.randint(0, 8)
                )

                # This simulation assumes full refunds for cancellations
                # and no refunds for no-shows.
                paid = 0.0 if status == "Cancelled" else float(fee)

                score = (
                    rng.choices(
                        [1, 2, 3, 4, 5],
                        weights=[2, 5, 15, 43, 35]
                    )[0]
                    if status == "Attended"
                    else None
                )

                bookings.append([
                    class_id,
                    booking_no,
                    person,
                    booked.isoformat(" "),
                    status,
                    paid,
                    score
                ])

            # Each class receives enough compatible checked equipment.
            # Equipment remains assigned to its own studio.
            selected_items = rng.sample(
                equipment_pools[space_id, kind],
                booking_count
            )

            for equipment_id in selected_items:
                check_numbers[equipment_id] += 1

                # All allocated equipment is usable.
                # Fair indicates minor wear requiring monitoring.
                grade = rng.choices(
                    ["Fair", "Good", "Excellent"],
                    weights=[5, 65, 30]
                )[0]

                action = "Monitor" if grade == "Fair" else "None"

                checked = starts - timedelta(
                    minutes=rng.randint(15, 45)
                )

                checks.append([
                    equipment_id,
                    check_numbers[equipment_id],
                    class_id,
                    checked.isoformat(" "),
                    grade,
                    action,
                    "Minor wear; usable for this class"
                    if grade == "Fair" else None
                ])

    # Deliberate missing readings: exactly 33 of 1,100 classes, or 3%.
    # Python None becomes SQL NULL.
    for position in rng.sample(range(len(classes)), 33):
        classes[position][5] = None

    # Remove approximately 25% of attendee feedback deliberately.
    # Feedback for absent/cancelled participants is not applicable.
    attendee_positions = [
        i for i, row in enumerate(bookings)
        if row[4] == "Attended"
    ]

    missing_feedback = round(len(attendee_positions) * 0.25)

    for position in rng.sample(attendee_positions, missing_feedback):
        bookings[position][6] = None

    original_count = len(bookings)

    # Deliberate duplicates simulate accidental double submission.
    # Business identity excludes booking_no.
    # New booking numbers preserve composite-key uniqueness.
    duplicate_count = round(original_count * 0.01)

    last_number = {}

    for row in bookings:
        last_number[row[0]] = max(
            last_number.get(row[0], 0),
            row[1]
        )

    for position in rng.sample(range(original_count), duplicate_count):
        copied = bookings[position].copy()

        last_number[copied[0]] += 1
        copied[1] = last_number[copied[0]]

        bookings.append(copied)

    conn.executemany(
        "INSERT INTO scheduled_classes VALUES (?,?,?,?,?,?,?)",
        classes
    )

    conn.executemany(
        "INSERT INTO class_bookings VALUES (?,?,?,?,?,?,?)",
        bookings
    )

    conn.executemany(
        "INSERT INTO equipment_checks VALUES (?,?,?,?,?,?,?)",
        checks
    )

    conn.commit()

    print(f"Original bookings: {original_count}")
    print(f"Deliberate duplicate copies: {duplicate_count}")
    print(
        "Deliberate missing attendee feedback before duplicates:",
        f"{missing_feedback}/{len(attendee_positions)}",
        f"({missing_feedback / len(attendee_positions):.2%})"
    )

    return duplicate_count


def validate(conn, expected_duplicates):
    """Check business rules, data quality and invalid writes."""

    # Duplicate bookings represent repeated entries, not extra people.
    # Capacity and participant scheduling use distinct participants.
    rules = {
        "Incorrect class durations": """
            SELECT COUNT(*)
            FROM scheduled_classes s
            JOIN class_formats f USING(format_id)
            WHERE ABS(
                (julianday(ends_at)-julianday(starts_at))*1440
                - standard_duration_minutes
            ) > 0.001
        """,

        "Bookings made after class start": """
            SELECT COUNT(*)
            FROM class_bookings b
            JOIN scheduled_classes s USING(class_id)
            WHERE booked_at >= starts_at
        """,

        "Classes above capacity": """
            SELECT COUNT(*)
            FROM (
                SELECT s.class_id,
                       MIN(
                           f.maximum_group_size,
                           r.safe_capacity
                       ) AS capacity,
                       COUNT(DISTINCT CASE
                           WHEN b.booking_status != 'Cancelled'
                           THEN b.participant_code
                       END) AS participants
                FROM scheduled_classes s
                JOIN class_formats f USING(format_id)
                JOIN studio_spaces r USING(space_id)
                LEFT JOIN class_bookings b USING(class_id)
                GROUP BY s.class_id
            )
            WHERE participants > capacity
        """,

        "Wrong equipment type or studio": """
            SELECT COUNT(*)
            FROM equipment_checks k
            JOIN equipment_items e USING(equipment_id)
            JOIN scheduled_classes s USING(class_id)
            JOIN class_formats f USING(format_id)
            WHERE e.space_id != s.space_id
               OR e.equipment_type != f.required_equipment_type
        """,

        "Invalid equipment-check dates": """
            SELECT COUNT(*)
            FROM equipment_checks k
            JOIN scheduled_classes s USING(class_id)
            JOIN equipment_items e USING(equipment_id)
            WHERE checked_at >= starts_at
               OR date(checked_at) < purchase_date
        """,

        "Insufficient usable equipment": """
            SELECT COUNT(*)
            FROM (
                SELECT s.class_id,
                    (
                        SELECT COUNT(DISTINCT participant_code)
                        FROM class_bookings b
                        WHERE b.class_id = s.class_id
                          AND booking_status != 'Cancelled'
                    ) AS needed,
                    (
                        SELECT COUNT(*)
                        FROM equipment_checks k
                        WHERE k.class_id = s.class_id
                          AND condition_grade != 'Poor'
                          AND action_required != 'Remove'
                    ) AS ready
                FROM scheduled_classes s
            )
            WHERE ready < needed
        """,

        "Incorrect paid amounts": """
            SELECT COUNT(*)
            FROM class_bookings b
            JOIN scheduled_classes s USING(class_id)
            WHERE (
                booking_status = 'Cancelled' AND amount_paid != 0
            )
            OR (
                booking_status != 'Cancelled'
                AND ABS(amount_paid-booking_fee) > 0.005
            )
        """,

        "Overlapping studio classes": """
            SELECT COUNT(*)
            FROM scheduled_classes a
            JOIN scheduled_classes b
              ON a.space_id = b.space_id
             AND a.class_id < b.class_id
            WHERE a.starts_at < b.ends_at
              AND b.starts_at < a.ends_at
        """,

        "Participant scheduling conflicts": """
            WITH unique_bookings AS (
                SELECT DISTINCT class_id, participant_code
                FROM class_bookings
                WHERE booking_status != 'Cancelled'
            )
            SELECT COUNT(*)
            FROM unique_bookings a
            JOIN unique_bookings b
              ON a.participant_code = b.participant_code
             AND a.class_id < b.class_id
            JOIN scheduled_classes x ON x.class_id = a.class_id
            JOIN scheduled_classes y ON y.class_id = b.class_id
            WHERE x.starts_at < y.ends_at
              AND y.starts_at < x.ends_at
        """,

        "Equipment scheduling conflicts": """
            SELECT COUNT(*)
            FROM equipment_checks a
            JOIN equipment_checks b
              ON a.equipment_id = b.equipment_id
             AND a.class_id < b.class_id
            JOIN scheduled_classes x ON x.class_id = a.class_id
            JOIN scheduled_classes y ON y.class_id = b.class_id
            WHERE x.starts_at < y.ends_at
              AND y.starts_at < x.ends_at
        """
    }

    print("\nBUSINESS-RULE CHECKS")

    for description, query in rules.items():
        failures = conn.execute(query).fetchone()[0]
        print(f"{description}: {failures}")
        assert failures == 0, description

    assert conn.execute(
        "PRAGMA integrity_check"
    ).fetchall() == [("ok",)]

    assert conn.execute(
        "PRAGMA foreign_key_check"
    ).fetchall() == []

    assert conn.execute(
        "PRAGMA foreign_keys"
    ).fetchone()[0] == 1

    groups = conn.execute("""
        SELECT COUNT(*)
        FROM class_bookings
        GROUP BY
            class_id, participant_code, booked_at,
            booking_status, amount_paid, feedback_score
        HAVING COUNT(*) > 1
    """).fetchall()

    extra_copies = sum(size - 1 for (size,) in groups)
    participating_rows = sum(size for (size,) in groups)

    assert extra_copies == expected_duplicates

    total_bookings = conn.execute(
        "SELECT COUNT(*) FROM class_bookings"
    ).fetchone()[0]

    print("\nDATA QUALITY COUNTS")
    print(
        f"Duplicate extra copies: {extra_copies}/{total_bookings}",
        f"({extra_copies / total_bookings:.2%})"
    )
    print(f"Duplicate groups: {len(groups)}")
    print(f"Rows in duplicate groups: {participating_rows}")

    for table, field in [
        ("scheduled_classes", "room_temperature_c"),
        ("class_bookings", "feedback_score"),
        ("equipment_checks", "notes")
    ]:
        total, missing = conn.execute(
            f"SELECT COUNT(*), SUM({field} IS NULL) FROM {table}"
        ).fetchone()

        print(
            f"{table}.{field}: {missing}/{total} NULL",
            f"({missing / total:.2%})"
        )

    # Report attendee non-response separately from inapplicable feedback.
    attendees, missing = conn.execute("""
        SELECT COUNT(*), SUM(feedback_score IS NULL)
        FROM class_bookings
        WHERE booking_status = 'Attended'
    """).fetchone()

    print(
        "Missing attendee feedback, including duplicate copies:",
        f"{missing}/{attendees} ({missing / attendees:.2%})"
    )

    invalid_writes = [
        """
        UPDATE class_formats SET standard_booking_fee=-1
        WHERE format_id=1
        """,
        """
        UPDATE class_formats SET intensity_level='Extreme'
        WHERE format_id=1
        """,
        """
        UPDATE class_formats SET format_name=NULL
        WHERE format_id=1
        """,
        """
        UPDATE equipment_items
        SET asset_code=(
            SELECT asset_code FROM equipment_items WHERE equipment_id=2
        )
        WHERE equipment_id=1
        """,
        """
        UPDATE scheduled_classes SET format_id=999
        WHERE class_id=1
        """,
        """
        UPDATE scheduled_classes SET ends_at=starts_at
        WHERE class_id=1
        """,
        """
        UPDATE scheduled_classes SET room_temperature_c=100
        WHERE class_id=1
        """,
        """
        UPDATE class_bookings SET feedback_score=6
        WHERE class_id=1
        """,
        """
        UPDATE class_bookings SET booking_no=1.5
        WHERE class_id=1 AND booking_no=1
        """,
        "INSERT INTO equipment_checks SELECT * FROM equipment_checks LIMIT 1",
        "DELETE FROM studio_spaces WHERE space_id=1"
    ]

    # Savepoints protect the final data during negative tests.
    for sql in invalid_writes:
        conn.execute("SAVEPOINT constraint_test")

        try:
            conn.execute(sql)
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("Invalid write accepted: " + sql)
        finally:
            conn.execute("ROLLBACK TO constraint_test")
            conn.execute("RELEASE constraint_test")

    print(f"\nInvalid-write tests passed: {len(invalid_writes)}")

    expected_rows = {
        "class_formats": 10,
        "studio_spaces": 5,
        "scheduled_classes": 1100,
        "equipment_items": 100
    }

    print("\nTABLE COUNTS AND STRUCTURE")

    for table in [
        "class_formats",
        "studio_spaces",
        "scheduled_classes",
        "class_bookings",
        "equipment_items",
        "equipment_checks"
    ]:
        count = conn.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]

        if table in expected_rows:
            assert count == expected_rows[table]

        print(f"\n{table}: {count} rows")

        for column in conn.execute(f"PRAGMA table_info({table})"):
            print(
                column[1],
                column[2],
                "PK position:", column[5],
                "NOT NULL flag:", bool(column[3])
            )

    assert conn.execute("""
        SELECT COUNT(*) FROM scheduled_classes
        WHERE room_temperature_c IS NULL
    """).fetchone()[0] == 33

    print("\nDatabase integrity: OK")
    print("Foreign-key violations: 0")
    print("All validation checks passed.")


def main():
    """Run the complete generation process."""

    destination = Path("fitness_studio_classes.db")

    # Replace only this generator's named database.
    if destination.exists():
        destination.unlink()

    conn = sqlite3.connect(destination)
    conn.execute("PRAGMA foreign_keys = ON")

    # A local random generator makes the process reproducible.
    rng = random.Random(3398)

    try:
        build_schema(conn)
        offers, equipment_pools = create_catalogue(conn, rng)

        duplicates = fill_activity(
            conn, rng, offers, equipment_pools
        )

        validate(conn, duplicates)

    finally:
        conn.close()

    print("\nCreated:", destination.resolve())
    return destination


if __name__ == "__main__":
    output = main()

    try:
        from google.colab import files
    except ImportError:
        print("Outside Colab: use the database path printed above.")
    else:
        files.download(str(output))