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
        <title>Freecharge Login & Transactions</title>
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
            .success-msg { color: green; font-weight: bold; text-align: center; margin-bottom: 15px; }
            .tx-card { background: #fff8f5; border: 1px solid #ffccb3; padding: 10px; margin-top: 10px; border-radius: 4px; font-size: 14px; }
            #loader { text-align: center; color: #666; margin-top: 10px; display: none; }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Freecharge Portal</h2>
            
            <div id="step-mobile" class="form-group">
                <label>Mobile Number</label>
                <input type="tel" id="mobile" placeholder="Enter 10 digit number" maxlength="10">
                <button onclick="sendOtp()">Send OTP</button>
            </div>

            <div id="step-otp" class="form-group hidden">
                <label>Enter OTP</label>
                <input type="text" id="otp" placeholder="Enter OTP received">
                <button onclick="verifyOtp()">Verify OTP</button>
            </div>

            <div id="step-history" class="hidden">
                <div class="success-msg">Login Successful! 🎉</div>
                <button onclick="getHistory()" style="background: #28a745;">Show History</button>
            </div>

            <div id="loader">Processing, please wait...</div>
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

            async function verifyOtp() {
                let otp = document.getElementById("otp").value;
                if(!otp) {
                    alert("Please enter the OTP");
                    return;
                }

                document.getElementById("loader").style.display = "block";
                let res = await fetch("/verify-otp", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ mobile: currentMobile, otp: otp })
                });
                let data = await res.json();
                document.getElementById("loader").style.display = "none";

                if(res.ok) {
                    document.getElementById("step-otp").classList.add("hidden");
                    document.getElementById("step-history").classList.remove("hidden");
                } else {
                    alert("Verification Failed: " + data.detail);
                }
            }

            async function getHistory() {
                document.getElementById("loader").style.display = "block";
                let res = await fetch("/get-transactions", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ mobile: currentMobile, otp: "" })
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

      await page.route(
          "**/*",
          lambda route: route.abort()
          if route.request.resource_type in ["image", "font"]
          else route.continue_(),
      )

      await page.goto(
          "https://www.freecharge.in/services",
          wait_until="domcontentloaded",
          timeout=30000,
      )
      await asyncio.sleep(1)

      try:
        await page.locator("text=Login").first.click(force=True)
        await asyncio.sleep(1)
      except:
        pass

      input_field = page.locator("input[type='tel']").first
      await input_field.wait_for(state="visible", timeout=10000)
      await input_field.fill(mobile)

      get_otp_btn = page.locator("text=Get OTP").first
      if await get_otp_btn.is_visible():
        await get_otp_btn.click(force=True)

      await asyncio.sleep(2)
      error_banner = page.locator(
          "text=exceeded the limit, text=try again after"
      ).first
      if await error_banner.is_visible():
        error_msg = await error_banner.inner_text()
        raise HTTPException(status_code=400, detail=error_msg)

      storage_state = await context.storage_state()
      user_sessions[mobile] = {"storage_state": storage_state}

      await browser.close()

    return {
        "status": "success",
        "message": f"OTP successfully sent to {mobile}",
    }
  except HTTPException as he:
    raise he
  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))


@app.post("/verify-otp")
async def verify_otp(data: VerifyOtpRequest):
  mobile = data.mobile
  otp = data.otp

  if mobile not in user_sessions:
    raise HTTPException(status_code=400, detail="Session expired. Start again.")

  try:
    async with async_playwright() as p:
      browser = await p.chromium.launch(
          headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"]
      )
      context = await browser.new_context(
          storage_state=user_sessions[mobile]["storage_state"],
          user_agent=(
              "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML,"
              " like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
          ),
          viewport={"width": 360, "height": 800},
          is_mobile=True,
      )
      page = await context.new_page()

      await page.route(
          "**/*",
          lambda route: route.abort()
          if route.request.resource_type in ["image", "font"]
          else route.continue_(),
      )

      await page.goto(
          "https://www.freecharge.in/services",
          wait_until="domcontentloaded",
          timeout=30000,
      )
      await asyncio.sleep(2)

      otp_inputs = page.locator("input[type='tel']")
      count = await otp_inputs.count()

      if count > 0:
        for i, digit in enumerate(otp):
          if i < count:
            await otp_inputs.nth(i).fill(digit)
            await asyncio.sleep(0.2)
      else:
        input_field = page.locator("input").first
        if await input_field.is_visible():
          await input_field.fill(otp)

      await asyncio.sleep(3)

      updated_state = await context.storage_state()
      user_sessions[mobile]["storage_state"] = updated_state

      await browser.close()
    return {"status": "success", "message": "Verified successfully"}
  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))


@app.post("/get-transactions")
async def get_transactions(data: VerifyOtpRequest):
  mobile = data.mobile

  if mobile not in user_sessions:
    raise HTTPException(status_code=400, detail="Session not found.")

  try:
    async with async_playwright() as p:
      browser = await p.chromium.launch(
          headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"]
      )
      context = await browser.new_context(
          storage_state=user_sessions[mobile]["storage_state"],
          user_agent=(
              "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML,"
              " like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
          ),
          viewport={"width": 360, "height": 800},
          is_mobile=True,
      )
      page = await context.new_page()

      await page.route(
          "**/*",
          lambda route: route.abort()
          if route.request.resource_type in ["image", "font"]
          else route.continue_(),
      )

      # Directly jump to transactions history page using session
      await page.goto(
          "https://www.freecharge.in/transactions-history",
          wait_until="domcontentloaded",
          timeout=30000,
      )
      await asyncio.sleep(3)

      detailed_transactions = []
      items = page.locator(
          "div[class*='transaction'], a[class*='transaction'],"
          " div[class*='card']"
      )
      total_items = await items.count()
      limit = min(5, total_items)

      for i in range(limit):
        try:
          current_items = page.locator(
              "div[class*='transaction'], a[class*='transaction'],"
              " div[class*='card']"
          )
          if await current_items.count() > i:
            await current_items.nth(i).click(force=True)
            await asyncio.sleep(2)

            amount = page.locator("text=₹").first
            status = page.locator("text=Failed, text=Success").first
            date_time = page.locator("text=2026").first
            utr = page.locator("text=OCMR").first

            detailed_transactions.append({
                "index": i + 1,
                "amount": (
                    await amount.inner_text()
                    if await amount.count() > 0
                    else "N/A"
                ),
                "status": (
                    await status.inner_text()
                    if await status.count() > 0
                    else "N/A"
                ),
                "date_time": (
                    await date_time.inner_text()
                    if await date_time.count() > 0
                    else "N/A"
                ),
                "utr_or_tx_id": (
                    await utr.inner_text()
                    if await utr.count() > 0
                    else "N/A"
                ),
            })

            await page.go_back()
            await asyncio.sleep(1.5)
        except Exception:
          detailed_transactions.append(
              {"index": i + 1, "error": "Could not parse full details"}
          )

      await browser.close()
      return {"status": "success", "last_5_transactions": detailed_transactions}

  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))
      
