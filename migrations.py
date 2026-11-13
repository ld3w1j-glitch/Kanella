"""Migrações locais preservando reservas e vínculos de horários existentes."""


def allow_booking_cancellation(db):
    sql = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='bookings'").fetchone()[0]
    if "'cancelled'" in sql:
        return
    # SQLite generalized ALTER TABLE: create/copy/drop/rename inside a transaction.
    # https://www.sqlite.org/lang_altertable.html#making_other_kinds_of_table_schema_changes
    db.execute('PRAGMA foreign_keys=OFF')
    try:
        db.execute('BEGIN IMMEDIATE')
        sql = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='bookings'").fetchone()[0]
        if "'cancelled'" not in sql:
            objects = db.execute("SELECT sql FROM sqlite_master WHERE tbl_name='bookings' AND type IN ('index','trigger') AND sql IS NOT NULL").fetchall()
            revised = sql.replace('CREATE TABLE bookings', 'CREATE TABLE bookings_new', 1).replace("'completed'", "'completed','cancelled'", 1)
            if revised == sql or 'CREATE TABLE bookings_new' not in revised:
                raise RuntimeError('Formato inesperado da tabela de reservas.')
            db.execute(revised)
            db.execute('INSERT INTO bookings_new SELECT * FROM bookings')
            db.execute('DROP TABLE bookings')
            db.execute('ALTER TABLE bookings_new RENAME TO bookings')
            for item in objects:
                db.execute(item[0])
            if db.execute('PRAGMA foreign_key_check').fetchone():
                raise RuntimeError('Falha na integridade dos vínculos da reserva.')
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.execute('PRAGMA foreign_keys=ON')
