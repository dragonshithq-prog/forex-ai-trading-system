@echo off
ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=60 -R 80:localhost:8003 nokey@localhost.run > "C:\Users\USER\Desktop\Forex Trading Bot\tunnel_final.log" 2>&1
