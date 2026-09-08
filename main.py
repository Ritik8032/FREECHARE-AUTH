import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from playwright.async_api import async_playwright

app = FastAPI()

user_sessions = {}


class SendOtpRequest(BaseModel):
  mobile: str


class VerifyOtpRequest(BaseModel):
  mobile: str
  otp: str


@app.get("/", response_class=HTMLResponse)
async def home():
  return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Freecharge Transaction Viewer</title>
        <style>
            body { font-family: Arial, sans-serif; background: #f4f4f9; margin: 0; padding: 20px; display: flex; justify-content: center; }
            .container { background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); width: 100%; max-width: 400px; }
            h2 { color: #ff6600; text-align: center; }
            .form-group { margin-bottom: 15px; }
            label { display: block; margin-bottom: 5px; font-weight: bold; }
            input { width: 100%; padding: 10px; box-sizing: border-box; border: 1px solid #ccc; border-radius: 4px; font-size: 16px; }
            button { width: 100%; background: #ff6600; color: white; border: none; padding: 10px; border-radius: 4px; font-size: 16px; cursor: pointer; margin-top: 10px; }
            button:hover { background: #e05b00; }
            .hidden { display: none; }
            .tx-card { background: #fff8f5; border: 1px solid #ffccb3; padding: 10px; margin-top: 10px; border-radius: 4px; font-size: 14px; }
            #loader { text-align: center; color: #666; margin-top: 10px; display: none; }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Freecharge Transactions</h2>
            
            <div id="step-mobile" class="form-group">
                <label>Mobile Number</label>
                <input type="tel" id="mobile" placeholder="Enter 10 digit number" maxlength="10">
                <button onclick="sendOtp()">Send OTP</button>
            </div>

            <div id="step-otp" class="form-group hidden">
                <label>Enter OTP</label>
                <input type="text" id="otp" placeholder="Enter OTP received">
                <button onclick="getTransactions()">Verify & Get Transactions</button>
            </div>

            <div id="loader">Processing in background, please wait...</div>
            <div id="results"></div>
        </div>

        <script>
            let currentMobile = "";

            async function sendOtp() {
                currentMobile = document.getElementById("mobile").value;
                if(currentMobile.length !== 10) {
                    alert("Please enter a valid 10-digit mobile number");
                    return;
                }

                document.getElementById("loader").style.display = "block";

                let res = await fetch("/send-otp", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ mobile: currentMobile })
                });
                let data = await res.json();
                
                document.getElementById("loader").style.display = "none";

                if(res.ok) {
                    alert(data.message);
                    document.getElementById("step-mobile").classList.add("hidden");
                    document.getElementById("step-otp").classList.remove("hidden");
                } else {
                    alert("Error: " + data.detail);
                }
            }

            async function getTransactions() {
                let otp = document.getElementById("otp").value;
                if(!otp) {
                    alert("Please enter the OTP");
                    return;
                }

                document.getElementById("loader").style.display = "block";
                document.getElementById("results").innerHTML = "";

                let res = await fetch("/get-transactions", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ mobile: currentMobile, otp: otp })
                });
                let data = await res.json();

                document.getElementById("loader").style.display = "none";

                if(res.ok) {
                    let html = "<h3>Last Transactions:</h3>";
                    data.last_5_transactions.forEach(tx => {
                        html += `<div class="tx-card">
                            <b>Amount:</b> ${tx.amount || 'N/A'}<br>
                            <b>Status:</b> ${tx.status || 'N/A'}<br>
                            <b>Date/Time:</b> ${tx.date_time || 'N/A'}<br>
                            <b>UTR/ID:</b> ${tx.utr_or_tx_id || 'N/A'}
                        </div>`;
                    });
                    document.getElementById("results").innerHTML = html;
                } else {
                    alert("Error: " + data.detail);
                }
            }
        </script>
    </body>
    </html>
    """


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

      try:
        await page.locator("text=Login").first.click()
        await asyncio.sleep(2)
      except:
        pass

      input_field = page.locator("input[type='tel']").first
      await input_field.wait_for(state="visible", timeout=10000)
      await input_field.fill(mobile)

      get_otp_btn = page.locator("text=Get OTP").first
      if await get_otp_btn.is_visible():
        # Force click lagaya hai taaki loader click ko intercept na kare
        await get_otp_btn.click(force=True)

      await asyncio.sleep(3)
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

      await context.add_cookies(user_sessions[mobile]["cookies"])
      page = await context.new_page()

      await page.goto(
          "https://www.freecharge.in/services",
          wait_until="domcontentloaded",
          timeout=60000,
      )
      await asyncio.sleep(3)

      try:
        await page.locator("text=Login").first.click()
        await asyncio.sleep(2)
      except:
        pass

      input_field = page.locator("input[type='tel']").first
      if await input_field.is_visible():
        await input_field.fill(mobile)
        get_otp_btn = page.locator("text=Get OTP").first
        if await get_otp_btn.is_visible():
          await get_otp_btn.click(force=True)
        await asyncio.sleep(3)

      otp_inputs = page.locator("input[type='tel']")
      count = await otp_inputs.count()
      if count > 1:
        for i, digit in enumerate(otp):
          if i < count:
            await otp_inputs.nth(i).fill(digit)
      else:
        await input_field.fill(otp)

      await asyncio.sleep(5)

      hamburger = page.locator(
          "xpath=//header//div[contains(@class, 'flex')]//button | //div[contains(text(), '☰')]"
      ).first
      await hamburger.click(force=True)
      await asyncio.sleep(2)

      await page.locator("text=My Transactions").click(force=True)
      await asyncio.sleep(4)

      detailed_transactions = []
      items = page.locator("div[class*='transaction'], a[class*='transaction']")
      total_items = await items.count()
      limit = min(5, total_items)

      for i in range(limit):
        await page.goto(
            "https://www.freecharge.in/transactions-history",
            wait_until="domcontentloaded",
        )
        await asyncio.sleep(2)

        current_items = page.locator(
            "div[class*='transaction'], a[class*='transaction']"
        )
        if await current_items.count() > i:
          await current_items.nth(i).click(force=True)
          await asyncio.sleep(3)

          try:
            amount = await page.locator("text=₹").first.inner_text()
            status = await page.locator(
                "text=Failed, text=Success"
            ).first.inner_text()
            date_time = await page.locator("text=2026").first.inner_text()
            utr = await page.locator("text=OCMR").first.inner_text()

            detailed_transactions.append({
                "index": i + 1,
                "amount": amount,
                "status": status,
                "date_time": date_time,
                "utr_or_tx_id": utr,
            })
          except Exception:
            detailed_transactions.append({
                "index": i + 1,
                "error": "Could not parse full details",
            })

      await browser.close()
      return {"status": "success", "last_5_transactions": detailed_transactions}

  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))
