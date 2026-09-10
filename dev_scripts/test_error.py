import sqlite3


def main():
    conn = sqlite3.connect('F:/Crypto terminal 2/backend/tpt.db')
    row = conn.execute("SELECT error_message FROM scan_runs WHERE status='FAILED' ORDER BY started_at DESC LIMIT 1").fetchone()
    if row:
        print(row[0])
    else:
        print("No FAILED scans found.")
        
if __name__ == "__main__":
    main()
