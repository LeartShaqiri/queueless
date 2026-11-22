from pathlib import Path

import uvicorn

from main import PORT, lan_ip

if __name__ == "__main__":
    ip = lan_ip()
    print(f"""
  QueueLess is running  (auto-reloads when you save a file)
  ---------------------------------------------
  Home / QR code   http://localhost:{PORT}/
  Customer join    http://{ip}:{PORT}/join   (phones on the same Wi-Fi)
  Staff console    http://localhost:{PORT}/staff
  TV display       http://localhost:{PORT}/tv
  Manager dash     http://localhost:{PORT}/dashboard
  Admin            http://localhost:{PORT}/admin
  Business screen  http://localhost:{PORT}/biz/kfc   (any business slug)
  API docs         http://localhost:{PORT}/docs
""")
    here = Path(__file__).parent
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, log_level="warning",
                reload=True, reload_dirs=[str(here)], reload_excludes=[".venv/*", "*.db*"])
