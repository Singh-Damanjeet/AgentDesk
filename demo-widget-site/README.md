# AgentDesk widget demo

Run the demo from this directory while the AgentDesk backend and frontend are
running:

```bash
python -m http.server 3002
```

Open <http://localhost:3002> and add the exact demo origin
`http://localhost:3002` (or `http://127.0.0.1:3002`) to the Website Chat
settings in the AgentDesk dashboard.

The intentionally conflicting global `button` and `iframe` rules verify that
the widget launcher shadow root and iframe content remain isolated from the
host page.
