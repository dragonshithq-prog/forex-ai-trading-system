"""Simple script to start Next.js dev server."""
import subprocess, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
subprocess.Popen(
    ["node", "node_modules/next/dist/bin/next", "dev", "-p", "3001"],
    stdout=open("frontend.log", "w"),
    stderr=subprocess.STDOUT,
    creationflags=subprocess.CREATE_NO_WINDOW,
)
