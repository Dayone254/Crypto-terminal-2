import sqlite3


def run():
    print("Clearing zombie states...")
    with sqlite3.connect('tpt/data/backtest.db') as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE scan_runs SET status='FAILED', error_message='Zombied manually cleared' WHERE status='RUNNING'")
        conn.commit()
        print("Done clearing zombies.")

if __name__ == '__main__':
    run()
