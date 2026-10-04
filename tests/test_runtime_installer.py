"""Use the same Windows PowerShell noninteractive host as Electron."""
import hashlib
import json
import http.server
import subprocess
import threading
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/install-runtime.ps1'


@pytest.fixture
def download_server():
    payload = b'verified runtime artifact' * 16000
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/missing':
                self.send_error(404)
                return
            self.send_response(200)
            if self.path == '/artifact':
                self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload if self.path == '/artifact' else
                             (hashlib.sha256(payload).hexdigest() if self.path == '/good' else '0' * 64).encode())
        def log_message(self, *args):
            pass
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}', payload
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.mark.parametrize('endpoint,checksum,success', [('/artifact', '/good', True),
                                                    ('/artifact', '/bad', False),
                                                    ('/missing', '/good', False)])
def test_checked_download_in_noninteractive_powershell(tmp_path, download_server, endpoint, checksum, success):
    url, payload = download_server
    target = tmp_path / 'runtime artifact.bin'
    # Load only the actual download function via the PowerShell parser. No network mocks.
    runner = tmp_path / 'download-check.ps1'
    runner.write_text("""param($Installer,$Url,$Target,$Checksum)
$ErrorActionPreference='Stop'
$ast=[System.Management.Automation.Language.Parser]::ParseFile($Installer,[ref]$null,[ref]$null)
$definitions=$ast.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -in @('Checked-Download','Initialize-InstallerHost','Report-Progress')},$true)
foreach($definition in $definitions) { . ([scriptblock]::Create($definition.Extent.Text)) }
if(Get-Command Initialize-InstallerHost -ErrorAction SilentlyContinue) { Initialize-InstallerHost }
$script:stage='test';$script:completed=0
Checked-Download $Url $Target $Checksum
""", encoding='utf8')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy',
                             'Bypass', '-File', str(runner), str(SCRIPT), url + endpoint,
                             str(target), url + checksum], capture_output=True, timeout=30)
    assert (result.returncode == 0) == success, result.stderr.decode(errors='replace')
    if success:
        assert target.read_bytes() == payload
        events = [json.loads(line.removeprefix('AMBIENT_PROGRESS ')) for line in
                  result.stdout.decode().splitlines() if line.startswith('AMBIENT_PROGRESS ')]
        received = [e for e in events if e['phase'] == 'downloading']
        assert received and received[0]['downloaded'] == 0
        assert any(0 < e['downloaded'] < len(payload) for e in received)
        final = events[-1]
        assert final['downloaded'] == len(payload)
        assert final['total'] == (len(payload) if endpoint == '/artifact' else 0)
    elif checksum == '/bad':
        assert b'checksum' in result.stderr.lower()


def test_every_network_request_uses_basic_parsing():
    source = SCRIPT.read_text(encoding='utf8')
    calls = [line for line in source.splitlines() if 'Invoke-WebRequest ' in line]
    assert calls
    assert all('-UseBasicParsing' in line for line in calls)
