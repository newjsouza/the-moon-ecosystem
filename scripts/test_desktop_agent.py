import asyncio
from agents.desktop import DesktopAgent

async def test_agent():
    agent = DesktopAgent()
    print("Checking dependencies...")
    result = await agent._execute("check", action="health_check")
    print(f"Dependencies: {result.data}")
    
    if result.data.get("tesseract") and result.data.get("pytesseract"):
        print("\nAttempting OCR...")
        ocr_result = await agent.perform_ocr()
        if ocr_result.success:
            print(f"OCR Success! Text found: {ocr_result.data['text'][:100]}...")
        else:
            print(f"OCR Failed: {ocr_result.error}")
    else:
        print("\nOCR skipped: Tesseract missing.")

if __name__ == "__main__":
    asyncio.run(test_agent())
