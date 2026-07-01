# Plotting Guidelines

Repository figures should follow these defaults:

- Use Times New Roman for all visible text. In matplotlib, set `font.family` to `serif` and `font.serif` to `["Times New Roman", "Times", "DejaVu Serif"]`.
- Do not use figure-level titles or single-panel plot titles. Subplot subtitles are acceptable when they distinguish panels.
- Keep `fig/` for rendered figure outputs only, such as `.png` and `.pdf`.
- Write derived tabular summaries to `data/phenology_grape/derived/`, not to `fig/`.
