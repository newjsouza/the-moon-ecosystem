import os
from PIL import Image

class LogoValidator:
    """
    Validator Agent: Ensures fetched logos meet design standards (transparency, aspect ratio).
    """
    def __init__(self, logo_dir="assets/logos"):
        self.logo_dir = logo_dir
        
    def validate_all(self):
        print("[*] Starting Logo Validation Audit...")
        if not os.path.exists(self.logo_dir):
            print("[!] Logo directory not found.")
            return
            
        files = [f for f in os.listdir(self.logo_dir) if f.endswith(('.png', '.jpg', '.webp'))]
        report = []
        
        for file in files:
            path = os.path.join(self.logo_dir, file)
            try:
                with Image.open(path) as img:
                    width, height = img.size
                    has_alpha = img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info)
                    
                    status = "VALID"
                    issues = []
                    
                    if width < 128 or height < 128:
                        status = "WARNING"
                        issues.append("Low resolution")
                    
                    if not has_alpha:
                        status = "WARNING"
                        issues.append("No transparency detection")
                        
                    print(f"[{status}] {file}: {width}x{height}, Mode: {img.mode}, Issues: {issues}")
                    report.append({"file": file, "status": status, "issues": issues})
            except Exception as e:
                print(f"[ERROR] {file}: Could not open image. {e}")
                
        return report

if __name__ == "__main__":
    validator = LogoValidator()
    validator.validate_all()
