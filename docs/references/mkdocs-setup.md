# MkDocs Documentation Site Setup

This template includes a MkDocs documentation site that automatically deploys to GitHub Pages.

## Enable GitHub Pages

After your first push to `main`:

1. **Wait for workflow to complete:**
   ```bash
   gh run list --workflow=deploy-docs.yml --limit 1
   ```

2. **Configure Pages:**
   - Go to Settings → Pages
   - Source: "Deploy from a branch"
   - Branch: `gh-pages`, Folder: `/ (root)`
   - Save

3. **Access your site:**
   - `https://<username>.github.io/<repo-name>/`

> [!NOTE]
> GitHub Pages is free for public repos. Private repos require GitHub Pro, Team, or Enterprise.

---

## Customize Your Site

### Update Branding

**Site name** (`mkdocs.yml`):
```yaml
site_name: Your Project Name Docs
```

**Logo icon** (`mkdocs.yml`):
```yaml
theme:
  icon:
    logo: material/robot  # Browse: https://pictogrammers.com/library/mdi/
```

**Colors** (`docs/stylesheets/extra.css`):
```css
:root {
  --md-primary-fg-color:        #5517c0;  /* Main */
  --md-primary-fg-color--light: #8e5ee8;  /* Hover */
  --md-primary-fg-color--dark:  #2d0a70;  /* Active */
  --md-accent-fg-color:         #5517c0;  /* Accent */
}
```

### Add Your Documentation

1. Create markdown files in `docs/`
2. Add to navigation in `mkdocs.yml`:
   ```yaml
   nav:
     - Your Section:
       - Your Doc: your-doc.md
   ```

3. Preview locally:
   ```bash
   uv sync --group docs
   uv run mkdocs serve  # http://127.0.0.1:8000
   ```

---

## File Structure

```
docs/
├── README.md              # Home page
├── *.md                   # Guide docs
├── stylesheets/
│   └── extra.css         # Custom theme
└── references/           # Reference docs
```

GitHub-style alerts work automatically:

> [!NOTE]
> Informational callout example

---

## Resources

- [MkDocs Documentation](https://www.mkdocs.org/)
- [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/) - Theme and features
- [Material Icons](https://pictogrammers.com/library/mdi/) - Logo icons
