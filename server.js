const http = require('http');
const https = require('https');
const url = require('url');
const fs = require('fs');
const path = require('path');

const PORT = process.env.PORT || 3001;
const STATIC_ROOT = path.resolve(__dirname);

const ALLOWED_HOSTS = [
  'www.youtube.com',
  'noembed.com',
  'i.ytimg.com',
];

const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css':  'text/css',
  '.js':   'application/javascript',
  '.json': 'application/json',
  '.png':  'image/png',
  '.jpg':  'image/jpeg',
  '.ico':  'image/x-icon',
  '.svg':  'image/svg+xml',
  '.woff2':'font/woff2',
  '.woff': 'font/woff',
  '.ttf':  'font/ttf',
};

function isAllowed(targetUrl) {
  try {
    const parsed = new url.URL(targetUrl);
    return ALLOWED_HOSTS.some(h =>
      parsed.hostname === h || parsed.hostname.endsWith('.' + h)
    );
  } catch {
    return false;
  }
}

function serveStatic(req, res) {
  const reqPath = req.url.split('?')[0];
  let filePath = path.join(STATIC_ROOT, reqPath === '/' ? 'index.html' : reqPath);

  if (!filePath.startsWith(STATIC_ROOT)) {
    res.writeHead(403); res.end('Forbidden'); return;
  }

  const ext = path.extname(filePath).toLowerCase();
  fs.readFile(filePath, (err, data) => {
    if (err) {
      fs.readFile(path.join(STATIC_ROOT, 'index.html'), (e2, d2) => {
        if (e2) { res.writeHead(404); res.end('Not found'); return; }
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
        res.end(d2);
      });
      return;
    }
    res.writeHead(200, { 'Content-Type': MIME_TYPES[ext] || 'application/octet-stream' });
    res.end(data);
  });
}

function doProxy(targetUrl, res) {
  const parsed = url.parse(targetUrl);
  const lib = parsed.protocol === 'https:' ? https : http;
  const options = {
    hostname: parsed.hostname,
    port: parsed.port || (parsed.protocol === 'https:' ? 443 : 80),
    path: parsed.path,
    method: 'GET',
    headers: {
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
      'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
      'Accept-Language': 'en-US,en;q=0.5',
      'Accept-Encoding': 'identity',
      'Cache-Control': 'no-cache',
    },
  };

  const proxyReq = lib.request(options, (proxyRes) => {
    if ([301,302,303,307,308].includes(proxyRes.statusCode) && proxyRes.headers.location) {
      const loc = proxyRes.headers.location;
      const redirectUrl = loc.startsWith('http')
        ? loc
        : `${parsed.protocol}//${parsed.hostname}${loc}`;
      if (isAllowed(redirectUrl)) { doProxy(redirectUrl, res); return; }
    }
    res.writeHead(proxyRes.statusCode, {
      'Content-Type': proxyRes.headers['content-type'] || 'text/plain',
      'Access-Control-Allow-Origin': '*',
    });
    proxyRes.pipe(res);
  });

  proxyReq.on('error', (err) => {
    if (!res.headersSent) {
      res.writeHead(502, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: err.message }));
    }
  });

  proxyReq.setTimeout(15000, () => {
    proxyReq.destroy();
    if (!res.headersSent) {
      res.writeHead(504, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Upstream timeout' }));
    }
  });

  proxyReq.end();
}

const server = http.createServer((req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }

  const parsedReq = url.parse(req.url, true);

  if (parsedReq.pathname === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', uptime: Math.round(process.uptime()), port: PORT }));
    return;
  }

  if (parsedReq.pathname === '/proxy') {
    const targetUrl = parsedReq.query.url;
    if (!targetUrl) {
      res.writeHead(400, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Missing ?url= parameter' }));
      return;
    }
    if (!isAllowed(targetUrl)) {
      res.writeHead(403, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Domain not in allowlist' }));
      return;
    }
    doProxy(targetUrl, res);
    return;
  }

  serveStatic(req, res);
});

server.listen(PORT, '0.0.0.0', () => {
  const isRailway = !!process.env.RAILWAY_ENVIRONMENT;
  console.log('\n  ╔══════════════════════════════════════════════╗');
  if (isRailway) {
    console.log('  ║   Wavelength — running on Railway            ║');
  } else {
    console.log(`  ║   Wavelength → http://localhost:${PORT}          ║`);
  }
  console.log('  ╚══════════════════════════════════════════════╝\n');
  if (!isRailway) {
    console.log(`  App:    http://localhost:${PORT}`);
    console.log(`  Health: http://localhost:${PORT}/health\n`);
  }
});

process.on('SIGINT', () => { console.log('\nShutting down.\n'); server.close(() => process.exit(0)); });
process.on('SIGTERM', () => { server.close(() => process.exit(0)); });
