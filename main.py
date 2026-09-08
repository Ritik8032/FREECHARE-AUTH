import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from playwright.async_api import async_playwright

app = FastAPI()

# Temporary session storage (Production me Redis ya Database use karein)
user_sessions = {}


class SendOtpRequest(BaseModel):
  mobile: str


class VerifyOtpRequest(BaseModel):
  mobile: str
  otp: str


@app.post("/send-otp")
async def send_otp(data: SendOtpRequest):
  mobile = data.mobile
  try:
    async with async_playwright() as p:
      browser = await p.chromium.launch(
          headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"]
      )
      context = await browser.new_context(
          user_agent=(
              "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML,"
              " like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
          ),
          viewport={"width": 360, "height": 800},
          is_mobile=True,
      )
      page = await context.new_page()

      await page.goto(
          "https://www.freecharge.in/services",
          wait_until="domcontentloaded",
          timeout=60000,
      )
      await asyncio.sleep(3)

      # Login trigger
      try:
        await page.locator("text=Login").first.click()
        await asyncio.sleep(2)
      except:
        pass

      # Mobile number fill karein
      input_field = page.locator("input[type='tel']").first
      await input_field.wait_for(state="visible", timeout=10000)
      await input_field.fill(mobile)

      # Get OTP click
      get_otp_btn = page.locator("text=Get OTP").first
      if await get_otp_btn.is_visible():
        await get_otp_btn.click()

      # Cookies save karein taaki verification ke waqt session bana rahe
      cookies = await context.cookies()
      user_sessions[mobile] = {"cookies": cookies}

      await browser.close()

    return {
        "status": "success",
        "message": f"OTP successfully sent to {mobile}",
    }

  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))


@app.post("/get-transactions")
async def get_transactions(data: VerifyOtpRequest):
  mobile = data.mobile
  otp = data.otp

  if mobile not in user_sessions:
    raise HTTPException(
        status_code=400,
        detail="Session not found. Please request OTP first.",
    )

  try:
    async with async_playwright() as p:
      browser = await p.chromium.launch(
          headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"]
      )
      context = await browser.new_context(
          user_agent=(
              "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML,"
              " like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
          ),
          viewport={"width": 360, "height": 800},
          is_mobile=True,
      )

      # Purana session load karein
      await context.add_cookies(user_sessions[mobile]["cookies"])
      page = await context.new_page()

      await page.goto(
          "https://www.freecharge.in/services",
          wait_until="domcontentloaded",
          timeout=60000,
      )
      await asyncio.sleep(3)

      # Login popup kholen aur OTP enter karein
      try:
        await page.locator("text=Login").first.click()
        await asyncio.sleep(2)
      except:
        pass

      input_field = page.locator("input[type='tel']").first
      if await input_field.is_visible():
        await input_field.fill(mobile)
        await page.locator("text=Get OTP").first.click()
        await asyncio.sleep(3)

      # OTP input boxes fill karne ka logic (agar multiple boxes hon ya ek single input ho)
      # Freecharge OTP inputs ko target karein
      otp_inputs = page.locator("input[type='tel']")
      count = await otp_inputs.count()
      if count > 1:
        for i, digit in enumerate(otp):
          if i < count:
            await otp_inputs.nth(i).fill(digit)
      else:
        await input_field.fill(otp)

      await asyncio.sleep(5)  # Login complete hone ka wait

      # Hamburger menu (☰) par click karein
      hamburger = page.locator(
          "xpath=//header//div[contains(@class, 'flex')]//button | //div[contains(text(), '☰')]"
      ).first
      await hamburger.click()
      await asyncio.sleep(2)

      # 'My Transactions' par click karein
      await page.locator("text=My Transactions").click()
      await asyncio.sleep(4)

      # Transaction history page par top 5 transactions extract karein
      transaction_elements = page.locator(
          ".transaction-item-class"
      )  # DOM structure ke mutabiq selector adjust karein
      # Har ek transaction par click karke andar ki detail nikalne ka loop:
      detailed_transactions = []

      # List items count (max 5)
      items = page.locator(
          "div[class*='transaction'], a[class*='transaction']"
      )  # Generic list cards
      total_items = await items.count()
      limit = min(5, total_items)

      for i in range(limit):
        # Dobara list page par jaakar index click karna padta hai taaki stale element error na aaye
        await page.goto(
            "https://www.freecharge.in/transactions-history",
            wait_until="domcontentloaded",
        )
        await asyncio.sleep(2)

        current_items = page.locator(
            "div[class*='transaction'], a[class*='transaction']"
        )
        if await current_items.count() > i:
          await current_items.nth(i).click()
          await asyncio.sleep(3)

          # Detail page se data scrape karna (jaise screenshots me dikhaya gaya hai)
          try:
            title_text = await page.locator(
                "div, span"
            ).all_inner_texts()  // Ya specific selectors
            # Fields extract karein: Amount, Date/Time, Status, Service Number, UTR/Transaction ID
            amount = await page.locator("text=₹").first.inner_text()
            status = await page.locator(
                "text=Failed, text=Success"
            ).first.inner_text()
            date_time = (
                await page.locator("text=2026").first.inner_text()
            )  # Example selector
            utr = await page.locator(
                "text=OCMR"
            ).first.inner_text()  # Transaction ID / UTR

            detailed_transactions.append({
                "index": i + 1,
                "amount": amount,
                "status": status,
                "date_time": date_time,
                "utr_or_tx_id": utr,
            })
          except Exception as ex:
            detailed_transactions.append({
                "index": i + 1,
                "error": "Could not parse full details",
            })

      await browser.close()
      return {"status": "success", "last_5_transactions": detailed_transactions}

  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))
      
