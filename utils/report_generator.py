"""
utils/report_generator.py
Generates Premium reports from the research vault.
"""
import os
import json
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from utils.logger import setup_logger

logger = setup_logger("ReportGenerator")

class ReportGenerator:
    def __init__(self, vault_path="learning/research_vault", template_path="utils/templates"):
        self.vault_path = vault_path
        self.template_path = template_path
        self.env = Environment(loader=FileSystemLoader(self.template_path))

    def generate(self, output_file="research_report.html"):
        """Reads the vault and renders the HTML report."""
        try:
            files = [f for f in os.listdir(self.vault_path) if f.endswith('.json')]
            data = []
            for f in sorted(files, reverse=True)[:10]: # Last 10 researches
                with open(os.path.join(self.vault_path, f), 'r') as j:
                    data.append(json.load(j))

            template = self.env.get_template("content_report.html")
            html_out = template.render(
                date=datetime.now().strftime("%B %d, %Y - %H:%M"),
                data=data
            )

            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html_out)
            
            logger.info(f"Premium report generated: {output_file}")
            return True, output_file
        except Exception as e:
            logger.error(f"Failed to generate report: {e}")
            return False, str(e)

if __name__ == "__main__":
    gen = ReportGenerator()
    gen.generate()
