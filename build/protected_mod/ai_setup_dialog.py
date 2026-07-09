from compat import QtWidgets, QtCore
from orchestrator import PROVIDERS, PROVIDER_HELP_URLS, LITELLM_PROVIDERS, PROVIDER_ADAPTERS
import json, urllib.request, urllib.error, ssl
def _check_host_reachable(host, port=443, timeout=5):
    import socket
    try:
        addr = socket.getaddrinfo(host, port)[0][4][0]
    except socket.gaierror:
        return (False, f'DNS lookup failed for {host}')
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((addr, port))
        s.close()
        return (True, f'{host}:{port} reachable')
    except socket.timeout:
        return (False, f'Connection to {host} timed out')
    except OSError as e:
        return (False, f'{host}:{port} — {e.strerror or str(e)}')
    finally:
        try:
            s.close()
        except Exception:
            pass
def _test_connection(provider, api_key, api_url='', proxy_url=''):
    if not api_key and provider in LITELLM_PROVIDERS:
        return (False, 'No API key provided')
    if provider not in PROVIDER_ADAPTERS:
        return (False, f'Unknown provider: {provider}')
    diag = {}
    diag_hosts = ['api.deepseek.com', 'api.openai.com', 'google.com']
    if provider == 'anthropic':
        diag_hosts.append('api.anthropic.com')
    for test_host in diag_hosts:
        ok, detail = _check_host_reachable(test_host)
        diag[test_host] = (ok, detail)
    failed = [h for h, (ok, _) in diag.items() if not ok]
    if len(failed) >= len(diag_hosts):
        return (False, 'No internet connectivity detected:\n' + '\n'.join((f"  {h}: {('❌' if h in failed else '✅')} {d}" for h, (_, d) in diag.items())) + '\n\nCheck your network connection, VPN, or proxy settings.')
    adapter = PROVIDER_ADAPTERS[provider]
    default_model = PROVIDERS.get(provider, 'deepseek/deepseek-chat')
    try:
        result = adapter.completion(model=default_model, messages=[{'role': 'user', 'content': 'hi'}], api_key=api_key if api_key else None, api_url=api_url if api_url else None, stream=False, proxy_url=proxy_url or None)
        if result is not None:
            return (True, 'Connected! (200 OK)')
        return (False, 'Empty response')
    except Exception as ex:
        exc_type = type(ex).__name__
        msg = str(ex)
        try:
            import litellm
            if hasattr(litellm, 'AuthenticationError') and isinstance(ex, litellm.AuthenticationError):
                return (False, f"{exc_type}: Invalid API key — check the key at the provider's console")
            if hasattr(litellm, 'BadRequestError') and isinstance(ex, litellm.BadRequestError):
                return (False, f'{exc_type}: Bad request — check model name or message format\n{msg[:200]}')
            if hasattr(litellm, 'PermissionError') and isinstance(ex, litellm.PermissionError):
                return (False, f'{exc_type}: Key lacks permissions (403)')
            if hasattr(litellm, 'NotFoundError') and isinstance(ex, litellm.NotFoundError):
                return (False, f'{exc_type}: Endpoint or model not found — check the model name\n{msg[:200]}')
            if hasattr(litellm, 'RateLimitError') and isinstance(ex, litellm.RateLimitError):
                return (True, f'{exc_type}: Rate limited (429) — but key is valid')
        except ImportError:
            pass
        if 'authentication_error' in msg:
            return (False, f'{exc_type}: Invalid Anthropic API key — check the key at https://console.anthropic.com/settings/keys')
        if 'permission_error' in msg:
            return (False, f'{exc_type}: Anthropic key lacks permissions')
        if 'rate_limit_error' in msg:
            return (True, f'{exc_type}: Rate limited — but key is valid')
        if 'invalid_api_key' in msg:
            return (False, f'{exc_type}: Invalid API key')
        if '401' in msg:
            return (False, f'{exc_type}: Invalid API key (401 Unauthorized)')
        if '403' in msg:
            return (False, f'{exc_type}: Access forbidden (403) — key may lack permissions')
        if '429' in msg:
            return (True, f'{exc_type}: Rate limited (429) — but key is valid')
        if '500' in msg or 'Internal Server Error' in msg:
            return (False, f'{exc_type}: Provider server error (500) — try again later')
        if '502' in msg:
            return (False, f'{exc_type}: Provider bad gateway (502) — provider may be down')
        if '503' in msg:
            return (False, f'{exc_type}: Provider unavailable (503) — try again later')
        if 'Connection refused' in msg or 'connection refused' in msg or '10061' in msg:
            return (False, 'Connection refused — your network/firewall is blocking the connection.\n\nNetwork diagnostics:\n' + '\n'.join((f"  {h}: {('✅' if ok else '❌')} {d}" for h, (ok, d) in diag.items())) + '\n\nOptions: use Ollama (local) or configure a proxy via HTTPS_PROXY env var.')
        if 'Name or service not known' in msg or 'getaddrinfo' in msg:
            return (False, 'DNS lookup failed — check the API URL')
        if 'timed out' in msg or 'timeout' in msg:
            return (False, f'{exc_type}: Request timed out — check the API URL or network')
        if 'api_key' in msg.lower() or 'invalid key' in msg.lower():
            return (False, f'{exc_type}: Invalid API key')
        if 'No module named' in msg:
            pkg = msg.split("'")[1] if "'" in msg else 'litellm'
            return (False, f"Missing package: run 'pip install {pkg}'")
        if 'SSL' in msg:
            return (False, f'{exc_type}: SSL error — check your network/VPN settings')
        return (False, f'{exc_type}: {msg[:350]}')
def _test_ollama(url):
    try:
        tags_url = url.rstrip('/') + '/api/tags'
        ctx = ssl.create_default_context()
        req = urllib.request.Request(tags_url, method='GET')
        resp = urllib.request.urlopen(req, timeout=10, context=ctx)
        data = json.loads(resp.read().decode())
        models = data.get('models', [])
        return (True, f'Connected! {len(models)} model(s) available')
    except urllib.error.URLError as e:
        return (False, f'Connection failed: {e.reason}')
    except Exception as ex:
        return (False, f'Error: {ex}')
def show_ai_setup_dialog(sidebar):
    d = QtWidgets.QDialog(sidebar)
    d.setWindowTitle('⚿ API Keys')
    d.setMinimumWidth(520)
    d.setStyleSheet('\n        QDialog { background:\n        QLabel { color:\n        QLineEdit {\n            background:\n            border-radius:6px; padding:6px 10px; font-size:12px;\n        }\n        QLineEdit:focus { border-color:\n        QComboBox {\n            background:\n            border-radius:6px; padding:4px 8px; font-size:12px; min-width:140px;\n        }\n        QComboBox:hover { border-color:\n        QComboBox::drop-down { border:none; width:16px; }\n        QPushButton {\n            background:\n            border-radius:8px; padding:6px 16px; font-size:11px; font-weight:600;\n        }\n        QPushButton:hover { background:\n        QPushButton.test_ok { background:\n        QPushButton.test_fail { background:\n        QFrame.separator { color:\n    ')
    layout = QtWidgets.QVBoxLayout(d)
    layout.setSpacing(10)
    title = QtWidgets.QLabel('<b>⚿ API Keys</b>')
    title.setStyleSheet('font-size:14px;color:#e6edf3;')
    layout.addWidget(title)
    layout.addWidget(QtWidgets.QLabel('<b>Provider</b>'))
    std_provider = QtWidgets.QComboBox()
    for provider in sidebar._provider_order:
        std_provider.addItem(sidebar._pretty_provider(provider), provider)
    cur_provider = sidebar._current_provider()
    i = std_provider.findData(cur_provider)
    std_provider.setCurrentIndex(i if i >= 0 else 0)
    std_key = QtWidgets.QLineEdit()
    std_key.setEchoMode(QtWidgets.QLineEdit.Password)
    std_key.setText(sidebar.api_key)
    std_key.setPlaceholderText('Paste your API key')
    ollama_url_input = QtWidgets.QLineEdit()
    ollama_url_input.setPlaceholderText('http://localhost:11434')
    ollama_url_input.setText(getattr(sidebar, '_ollama_url', 'http://localhost:11434'))
    proxy_input = QtWidgets.QLineEdit()
    proxy_input.setPlaceholderText('http://proxy:port (leave blank if none)')
    proxy_input.setText(getattr(sidebar, '_proxy_url', ''))
    std_status = QtWidgets.QLabel('')
    std_status.setStyleSheet('font-size:11px;')
    std_test = QtWidgets.QPushButton('⏰ Test')
    std_test.setFixedWidth(70)
    std_link = QtWidgets.QLabel('')
    std_link.setOpenExternalLinks(True)
    std_link.setStyleSheet('font-size:11px;')
    def _refresh_std_link():
        p = std_provider.currentData() or 'deepseek'
        link = PROVIDER_HELP_URLS.get(p, '')
        if link:
            std_link.setText(f'<a href="{link}" style="color:#58a6ff;">Get {sidebar._pretty_provider(p)} key</a>')
            std_link.setVisible(True)
        else:
            std_link.setVisible(False)
    std_warning = QtWidgets.QLabel('⚠️ <b>Limited capabilities:</b> Local models lack specialized guides (gears, airfoils, etc.), detailed scene context, conversation memory, and auto-retry &mdash; keep prompts precise and simple.')
    std_warning.setWordWrap(True)
    std_warning.setStyleSheet('color:#ff6b6b;font-size:11px;padding:4px 0;')
    def _update_fields():
        is_ollama = std_provider.currentData() == 'ollama'
        std_key.setVisible(not is_ollama)
        ollama_url_input.setVisible(is_ollama)
        std_warning.setVisible(is_ollama)
        _refresh_std_link()
    std_provider.currentIndexChanged.connect(_update_fields)
    def _do_test():
        prov = std_provider.currentData() or 'deepseek'
        key = std_key.text().strip()
        url = ollama_url_input.text().strip()
        proxy = proxy_input.text().strip()
        if prov == 'anthropic' and key and (not key.startswith('sk-ant-')):
            std_status.setText("⚠️ Anthropic keys start with 'sk-ant-' — verify you pasted the correct key")
            std_status.setStyleSheet('color:#f7c96a;font-size:11px;')
            return
        std_status.setText('⏳ Testing...')
        std_status.setStyleSheet('color:#f7c96a;font-size:11px;')
        std_test.setEnabled(False)
        def _run():
            if prov == 'ollama':
                ok, msg = _test_ollama(url or 'http://localhost:11434')
            else:
                ok, msg = _test_connection(prov, key, '', proxy)
            d._test_result = (ok, msg)
        def _done():
            ok, msg = getattr(d, '_test_result', (False, 'No response'))
            cls = 'color:#22c55e;' if ok else 'color:#ff6b6b;'
            icon = '✅ ' if ok else '❌ '
            std_status.setStyleSheet(cls)
            std_status.setText(f'{icon}{msg}')
            std_test.setEnabled(True)
        import threading
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        timer = QtCore.QTimer(d)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: _poll_thread(d, thread, _done, timer))
        timer.start(100)
    def _poll_thread(dlg, t, cb, timer):
        if t.is_alive():
            timer.start(100)
            return
        cb()
    std_test.clicked.connect(_do_test)
    pk = QtWidgets.QHBoxLayout()
    pk.setSpacing(6)
    pk.addWidget(std_provider)
    pk.addWidget(std_key, 1)
    pk.addWidget(ollama_url_input, 1)
    pk.addWidget(std_test)
    layout.addLayout(pk)
    layout.addWidget(std_status)
    layout.addWidget(std_warning)
    layout.addWidget(std_link)
    layout.addWidget(QtWidgets.QLabel('<b>Proxy</b>'))
    layout.addWidget(proxy_input)
    _update_fields()
    _refresh_std_link()
    layout.addStretch()
    btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
    def _accept():
        provider = std_provider.currentData() or 'deepseek'
        key = std_key.text().strip()
        if provider != 'ollama':
            if sidebar._provider_requires_key(provider) and (not key):
                QtWidgets.QMessageBox.warning(d, 'API Key Required', f'Please enter an API key for {sidebar._pretty_provider(provider)}.')
                return
        else:
            sidebar._ollama_url = ollama_url_input.text().strip() or 'http://localhost:11434'
        sidebar._proxy_url = proxy_input.text().strip()
        pidx = sidebar._provider_combo.findData(provider)
        if pidx >= 0:
            sidebar._provider_combo.setCurrentIndex(pidx)
        sidebar.save(key, provider, model=sidebar.c_model, url=sidebar.c_url)
        d.accept()
    btns.accepted.connect(_accept)
    btns.rejected.connect(d.reject)
    layout.addWidget(btns)
    d.exec()
