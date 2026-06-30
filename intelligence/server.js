const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = process.env.PORT || 8080;
const DIR = __dirname;

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
};

const server = http.createServer((req, res) => {
  let filePath = path.join(DIR, req.url === '/' ? 'index.html' : req.url);
  filePath = path.normalize(filePath);

  if (!filePath.startsWith(DIR)) {
    res.writeHead(403);
    return res.end('Forbidden');
  }

  const ext = path.extname(filePath);
  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404, { 'Content-Type': 'text/html' });
      return res.end('<h1>404 - File not found</h1><p>The intelligence report file was not found. Run <code>node server.js</code> from the intelligence directory.</p>');
    }
    res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
    res.end(data);
  });
});

server.listen(PORT, () => {
  console.log('============================================');
  console.log('  GitHub Intelligence Report Server');
  console.log('============================================');
  console.log('');
  console.log(`  URL: http://localhost:${PORT}`);
  console.log('');
  console.log('  Press Ctrl+C to stop');
  console.log('============================================');
});
