# AgentDesk widget demo

This directory is a small external-site fixture for the V1 website widget. The
normal `index.html` is a polished AcmeFlow-style product page. The separate
`hostile-css.html` page is a regression fixture with intentionally aggressive
host-page CSS.

Run the demo while the AgentDesk backend and frontend are running:

```bash
cd demo-widget-site
python -m http.server 3002
```

Open <http://localhost:3002> and add the exact demo origin
`http://localhost:3002` to Website Chat settings in the AgentDesk dashboard.
If you open the site through `127.0.0.1`, configure that exact origin instead.

The one-script installation is already present in the page:

```html
<script
  src="http://127.0.0.1:8000/widget.js"
  data-project="local-default"
></script>
```

The backend must have an enabled `local-default` widget before the launcher can
create an anonymous session. Use the dashboard's Website Chat page to save the
allowed origin.

For the isolation check, open
<http://localhost:3002/hostile-css.html>. The global rules on that page should
change the host button, but not the launcher or the chat controls inside the
iframe.
