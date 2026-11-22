import uvicorn

from main import PORT, lan_ip

if __name__ == "__main__":
    ip = lan_ip()
    print(f"""
  QueueLess is running
  ---------------------------------------------
  Home / QR code   http://localhost:{PORT}/
  Customer join    http://{ip}:{PORT}/join   (phones on the same Wi-Fi)
  Staff console    http://localhost:{PORT}/staff
  TV display       http://localhost:{PORT}/tv
  Manager dash     http://localhost:{PORT}/dashboard
  API docs         http://localhost:{PORT}/docs
""")
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, log_level="warning")
