from nbconvert import MarkdownExporter
from traitlets.config import Config

c = Config()
c.TemplateExporter.exclude_input = True

exporter = MarkdownExporter(config=c)

body, resources = exporter.from_filename("latenzanalyse_plotly_dash_ready.ipynb")

with open("latenzanalyse_plotly_dash_ready.ipynb.md", "w", encoding="utf-8") as f:
    f.write(body)