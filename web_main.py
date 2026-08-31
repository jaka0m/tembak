import base64
import json
import os
from datetime import datetime
from pathlib import Path
from typing import cast, Optional, List, Dict, Any

from fastapi import FastAPI, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv


def clear_screen() -> None:
    """Clear terminal screen (Windows/Linux/Android terminal)."""
    os.system("cls" if os.name == "nt" else "clear")

load_dotenv()

from app.service.auth import AuthInstance
from app.service.bookmark import BookmarkInstance
from app.service.decoy import DecoyInstance
from app.client.ciam import get_otp, submit_otp
from app.client.engsel import (
    get_balance,
    get_tiering_info,
    get_package,
    get_family,
    unsubscribe,
    get_transaction_history,
    dashboard_segments,
    get_notification_detail,
    send_api_request,
)
from app.client.famplan import (
    get_family_data,
    change_member,
    remove_member,
    set_quota_limit,
    validate_msisdn,
)
from app.client.circle import (
    get_group_data,
    get_group_members,
    spending_tracker,
    invite_circle_member,
    remove_circle_member,
    accept_circle_invitation,
    get_bonus_data,
)
from app.client.encrypt import decrypt_circle_msisdn
from app.client.registration import dukcapil
from app.client.store.segments import get_segments
from app.client.store.search import get_family_list, get_store_packages
from app.client.store.redeemables import get_redeemables
from app.client.purchase.balance import settlement_balance
from app.client.purchase.qris import settlement_qris, get_qris_code
from app.client.purchase.ewallet import settlement_multipayment
from app.menus import purchase as purchase_menu
from app.menus.util import format_quota_byte
from app.type_dict import PaymentItem

clear_screen()

app = FastAPI(title="MYnyak Engsel Sunset Web UI")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "web" / "templates"))

def render(template_name: str, context: dict) -> HTMLResponse:
    request = context["request"]
    return templates.TemplateResponse(request=request, name=template_name, context=context)

def get_context(request: Request, msg: str = "", err: str = "") -> dict:
    try:
        active_user = AuthInstance.get_active_user()
    except Exception:
        active_user = None

    return {
        "request": request,
        "active_user": active_user,
        "msg": msg,
        "err": err,
    }

def get_active_auth_ctx():
    try:
        active_user = AuthInstance.get_active_user()
        if not active_user:
            return None, None
        return AuthInstance.api_key, active_user.get("tokens")
    except Exception:
        return None, None



# ================= DASHBOARD =================
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, msg: str = "", err: str = ""):
    context = get_context(request, msg=msg, err=err)
    active_user = context.get("active_user")

    profile = None
    if active_user:
        try:
            api_key = AuthInstance.api_key
            tokens = active_user.get("tokens")
            balance = get_balance(api_key, tokens["id_token"]) if tokens else {}

            balance_remaining = balance.get("remaining", "0") if isinstance(balance, dict) else "0"
            balance_expired_at = balance.get("expired_at") if isinstance(balance, dict) else None
            expired_at_dt = (
                datetime.fromtimestamp(balance_expired_at).strftime("%Y-%m-%d %H:%M")
                if balance_expired_at else "N/A"
            )

            point_info = "Points: N/A | Tier: N/A"
            if active_user.get("subscription_type") == "PREPAID":
                tiering_data = get_tiering_info(api_key, tokens) if tokens else {}
                if isinstance(tiering_data, dict):
                    tier = tiering_data.get("tier", 0)
                    current_point = tiering_data.get("current_point", 0)
                    point_info = f"Points: {current_point} | Tier: {tier}"

            profile = {
                "number": active_user["number"],
                "subscriber_id": active_user.get("subscriber_id", "N/A"),
                "subscription_type": active_user.get("subscription_type", "N/A"),
                "balance": balance_remaining,
                "balance_expired_at": expired_at_dt,
                "point_info": point_info,
            }
        except Exception:
            profile = {
                "number": active_user["number"],
                "subscriber_id": active_user.get("subscriber_id", "N/A"),
                "subscription_type": active_user.get("subscription_type", "N/A"),
                "balance": "N/A",
                "balance_expired_at": "N/A",
                "point_info": "Points: N/A | Tier: N/A",
            }

    context["profile"] = profile
    return render("index.html", context)


# ================= ACCOUNTS / AUTH =================
@app.get("/accounts", response_class=HTMLResponse)
@app.get("/u/account", response_class=HTMLResponse)
async def accounts_page(request: Request, msg: str = "", err: str = "", phone: str = "", otp_sent: bool = False):
    context = get_context(request, msg=msg, err=err)
    try:
        AuthInstance.load_tokens()
        context["users"] = AuthInstance.refresh_tokens
    except Exception:
        context["users"] = []
    context["phone"] = phone
    context["otp_sent"] = otp_sent
    return render("accounts.html", context)


@app.post("/accounts/request-otp", response_class=HTMLResponse)
async def request_otp_action(request: Request, phone: str = Form(...)):
    phone = phone.strip()
    if not phone.isdigit() or not phone.startswith("628"):
        return RedirectResponse(url="/accounts?err=Nomor+tidak+valid.+Format:+628xxxx", status_code=303)

    try:
        subscriber = get_otp(phone)
        if not subscriber:
            return RedirectResponse(url="/accounts?err=Gagal+request+OTP.+Periksa+nomor+atau+coba+lagi.", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/accounts?err=Error+request+OTP:+{str(e)}", status_code=303)

    return RedirectResponse(url=f"/accounts?phone={phone}&otp_sent=True&msg=Kode+OTP+telah+dikirim+ke+{phone}", status_code=303)


@app.post("/accounts/submit-otp", response_class=HTMLResponse)
async def submit_otp_action(request: Request, phone: str = Form(...), otp: str = Form(...)):
    phone = phone.strip()
    otp = otp.strip()

    try:
        tokens = submit_otp(AuthInstance.api_key, "SMS", phone, otp)
        if not tokens or not tokens.get("refresh_token"):
            return RedirectResponse(url=f"/accounts?phone={phone}&otp_sent=True&err=Kode+OTP+salah+atau+kadaluarsa.", status_code=303)

        AuthInstance.add_refresh_token(int(phone), tokens["refresh_token"])
        return RedirectResponse(url=f"/accounts?msg=Berhasil+login+dan+menambah+akun+{phone}", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/accounts?err=Error+submit+OTP:+{str(e)}", status_code=303)


@app.post("/accounts/switch", response_class=HTMLResponse)
async def switch_account_action(number: int = Form(...)):
    try:
        AuthInstance.set_active_user(number)
        return RedirectResponse(url=f"/accounts?msg=Akun+aktif+diganti+ke+{number}", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/accounts?err=Gagal+ganti+akun:+{str(e)}", status_code=303)


@app.post("/accounts/delete", response_class=HTMLResponse)
async def delete_account_action(number: int = Form(...)):
    try:
        active = context.get("active_user") if (context := get_context(None)) else None
        if active and active.get("number") == number:
            return RedirectResponse(url="/accounts?err=Tidak+bisa+menghapus+akun+yang+sedang+aktif.", status_code=303)

        AuthInstance.remove_refresh_token(number)
        return RedirectResponse(url=f"/accounts?msg=Akun+{number}+berhasil+dihapus.", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/accounts?err=Gagal+hapus+akun:+{str(e)}", status_code=303)


# ================= PACKAGES / MY PACKAGES =================
@app.get("/packages", response_class=HTMLResponse)
@app.get("/packages/my", response_class=HTMLResponse)
async def packages_page(request: Request, msg: str = "", err: str = ""):
    context = get_context(request, msg=msg, err=err)
    api_key, tokens = get_active_auth_ctx()

    packages = []
    if api_key and tokens:
        try:
            path = "api/v8/packages/quota-details"
            payload = {"is_enterprise": False, "lang": "en", "family_member_id": ""}
            res = send_api_request(api_key, path, payload, tokens["id_token"], "POST")
            if isinstance(res, dict) and res.get("status") == "SUCCESS":
                quotas = res.get("data", {}).get("quotas", [])
                for q in quotas:
                    name = q.get("name", "N/A")
                    benefits = q.get("benefits", [])
                    brief = ""
                    if benefits:
                        b = benefits[0]
                        dtype = b.get("data_type", "")
                        rem = b.get("remaining", 0)
                        tot = b.get("total", 0)
                        if dtype == "DATA":
                            brief = f"{format_quota_byte(rem)} / {format_quota_byte(tot)}"
                        elif dtype == "VOICE":
                            brief = f"{rem/60:.1f}/{tot/60:.1f} menit"
                        elif dtype == "TEXT":
                            brief = f"{rem}/{tot} SMS"

                    packages.append({
                        "name": name,
                        "quota_code": q.get("quota_code", ""),
                        "product_subscription_type": q.get("product_subscription_type", ""),
                        "product_domain": q.get("product_domain", ""),
                        "brief": brief,
                    })
            else:
                context["err"] = "Gagal mengambil daftar paket aktif."
        except Exception as e:
            context["err"] = f"Error mengambil paket: {str(e)}"

    context["packages"] = packages
    return render("packages.html", context)


@app.post("/packages/unsubscribe", response_class=HTMLResponse)
async def unsubscribe_action(
    quota_code: str = Form(...),
    product_subscription_type: str = Form(...),
    product_domain: str = Form(...),
):
    api_key, tokens = get_active_auth_ctx()
    if not api_key or not tokens:
        return RedirectResponse(url="/packages?err=Belum+ada+akun+aktif.", status_code=303)

    try:
        ok = unsubscribe(api_key, tokens, quota_code, product_subscription_type, product_domain)
        if ok:
            return RedirectResponse(url="/packages?msg=Berhasil+unsubscribe+paket.", status_code=303)
        return RedirectResponse(url="/packages?err=Gagal+unsubscribe+paket.", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/packages?err=Error+unsubscribe:+{str(e)}", status_code=303)


# ================= HOT & HOT2 =================
def load_hot_json(filename: str) -> list:
    filepath = BASE_DIR / "hot_data" / filename
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


@app.get("/hot", response_class=HTMLResponse)
async def hot_page(request: Request, msg: str = "", err: str = ""):
    context = get_context(request, msg=msg, err=err)
    context["title"] = "🔥 Paket HOT 🔥"
    raw_items = load_hot_json("hot.json")
    items = []
    for idx, item in enumerate(raw_items, start=1):
        order = item.get("order") or 1
        items.append({
            "order": order,
            "variant_name": item.get("variant_name") or item.get("family_name") or "N/A",
            "family_code": item.get("family_code", ""),
            "is_enterprise": "1" if item.get("is_enterprise") else "0",
            "display_name": f"{item.get('family_name', '')} - {item.get('option_name', '')}".strip(" -"),
            "price": item.get("price", "N/A"),
        })
    context["items"] = items
    return render("hot.html", context)


@app.get("/hot2", response_class=HTMLResponse)
async def hot2_page(request: Request, msg: str = "", err: str = ""):
    context = get_context(request, msg=msg, err=err)
    context["title"] = "🔥 Paket HOT-2 🔥"
    raw_items = load_hot_json("hot2.json")
    items = []
    for idx, item in enumerate(raw_items, start=1):
        packages = item.get("packages", [])
        p0 = packages[0] if packages else {}
        order = p0.get("order") or item.get("order") or 1
        items.append({
            "order": order,
            "variant_name": p0.get("variant_name") or item.get("name") or "N/A",
            "family_code": p0.get("family_code", item.get("family_code", "")),
            "is_enterprise": "1" if p0.get("is_enterprise", False) else "0",
            "display_name": item.get("name", "N/A"),
            "price": item.get("price", "N/A"),
            "detail": item.get("detail", ""),
        })
    context["items"] = items
    return render("hot.html", context)


# ================= OPTION & FAMILY CODES =================
@app.get("/packages/option", response_class=HTMLResponse)
@app.get("/packages/by-option", response_class=HTMLResponse)
@app.get("/packages/by-family", response_class=HTMLResponse)
async def option_family_page(request: Request, family_code: str = Query("", alias="code"), msg: str = "", err: str = ""):
    context = get_context(request, msg=msg, err=err)
    if not family_code:
        family_code = request.query_params.get("family_code", "")

    context["family_code"] = family_code
    context["family_name"] = ""
    context["options"] = []

    if family_code:
        api_key, tokens = get_active_auth_ctx()
        if api_key and tokens:
            try:
                data = get_family(api_key, tokens, family_code)
                if data:
                    context["family_name"] = data.get("package_family", {}).get("name", "N/A")
                    options = []
                    for variant in data.get("package_variants", []):
                        vname = variant.get("name", "N/A")
                        for opt in variant.get("package_options", []):
                            options.append({
                                "variant_name": vname,
                                "name": opt.get("name", "N/A"),
                                "price": opt.get("price", 0),
                                "order": opt.get("order", 0),
                                "package_option_code": opt.get("package_option_code", ""),
                            })
                    context["options"] = options
                else:
                    context["err"] = "Family Code tidak ditemukan atau gagal diambil."
            except Exception as e:
                context["err"] = f"Error mengambil data family code: {str(e)}"

    return render("option_family.html", context)


@app.post("/packages/loop-purchase", response_class=HTMLResponse)
@app.post("/purchase/family-loop", response_class=HTMLResponse)
async def loop_purchase_action(
    family_code: str = Form(...),
    start_option: int = Form(1),
    delay_seconds: int = Form(0),
):
    try:
        old_pause = purchase_menu.pause
        purchase_menu.pause = lambda: None
        purchase_menu.purchase_by_family(
            family_code=family_code,
            use_decoy=False,
            pause_on_success=False,
            delay_seconds=delay_seconds,
            start_from_option=start_option,
        )
        purchase_menu.pause = old_pause
        return RedirectResponse(url=f"/packages/option?family_code={family_code}&msg=Loop+purchase+selesai", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/packages/option?family_code={family_code}&err=Loop+purchase+error:+{str(e)}", status_code=303)


# ================= PACKAGE DETAIL & PURCHASES =================
@app.get("/packages/detail", response_class=HTMLResponse)
async def package_detail_page(
    request: Request,
    option_code: Optional[str] = "",
    family_code: Optional[str] = "",
    variant_name: Optional[str] = "",
    order: Optional[str] = "1",
    is_enterprise: Optional[str] = "0",
    msg: str = "",
    err: str = "",
):
    context = get_context(request, msg=msg, err=err)
    api_key, tokens = get_active_auth_ctx()

    if not api_key or not tokens:
        return RedirectResponse(url="/accounts?err=Belum+ada+akun+aktif.", status_code=303)

    target_option_code = option_code or ""

    # Defensively convert order and is_enterprise
    try:
        order_val = int(order) if order and str(order).isdigit() else 1
    except (ValueError, TypeError):
        order_val = 1

    is_enterprise_val = str(is_enterprise).lower() in ("1", "true", "yes")

    try:
        # Resolve from family_code + variant_name + order if option_code is empty
        if not target_option_code and family_code:
            family_data = get_family(api_key, tokens, family_code, is_enterprise_val)
            if family_data:
                for v in family_data.get("package_variants", []):
                    # Match variant_name if provided, otherwise check all variants
                    if not variant_name or v.get("name") == variant_name:
                        for opt in v.get("package_options", []):
                            if opt.get("order") == order_val:
                                target_option_code = opt.get("package_option_code", "")
                                break
                    if target_option_code:
                        break

        if not target_option_code:
            return RedirectResponse(url="/packages/option?err=Kode+paket+tidak+dapat+ditemukan.", status_code=303)

        package = get_package(api_key, tokens, target_option_code)
        if not package:
            return RedirectResponse(url=f"/packages/option?err=Gagal+mengambil+detail+paket+{target_option_code}", status_code=303)

        opt = package.get("package_option", {})
        fam = package.get("package_family", {})

        benefits_formatted = []
        for b in opt.get("benefits", []):
            btype = b.get("data_type", "")
            tot = b.get("total", 0)
            if btype == "DATA":
                tot_str = format_quota_byte(tot)
            elif btype == "VOICE":
                tot_str = f"{tot/60:.1f} menit"
            elif btype == "TEXT":
                tot_str = f"{tot} SMS"
            else:
                tot_str = str(tot)
            benefits_formatted.append(f"{b.get('name', '')} ({btype}): {tot_str}")

        context["package"] = {
            "name": f"{fam.get('name', '')} - {opt.get('name', '')}".strip(" -"),
            "option_code": target_option_code,
            "price": opt.get("price", 0),
            "validity": opt.get("validity", "0"),
            "point": opt.get("point", 0),
            "benefits": benefits_formatted,
            "family_code": fam.get("package_family_code", family_code or ""),
            "variant_name": variant_name or "",
            "option_name": opt.get("name", ""),
            "order": order_val,
            "is_enterprise": 1 if is_enterprise_val else 0,
        }
    except Exception as e:
        context["err"] = f"Error memuat detail paket: {str(e)}"

    return render("package_detail.html", context)


def get_payment_ctx(api_key: str, tokens: dict, option_code: str) -> dict | None:
    try:
        pkg = get_package(api_key, tokens, option_code)
        if not pkg:
            return None
        opt = pkg.get("package_option", {})
        fam = pkg.get("package_family", {})
        payment_for = fam.get("payment_for", "") or "BUY_PACKAGE"
        item = {
            "item_code": option_code,
            "product_type": "",
            "item_price": int(opt.get("price", 0)),
            "item_name": opt.get("name", "") or "Package",
            "tax": 0,
            "token_confirmation": pkg.get("token_confirmation", ""),
        }
        return {
            "option_code": option_code,
            "price": int(opt.get("price", 0)),
            "payment_for": payment_for,
            "items": [item],
        }
    except Exception:
        return None


@app.post("/packages/pay/balance", response_class=HTMLResponse)
async def pay_balance_action(option_code: str = Form(...)):
    api_key, tokens = get_active_auth_ctx()
    pctx = get_payment_ctx(api_key, tokens, option_code) if api_key and tokens else None
    if not pctx:
        return RedirectResponse(url=f"/packages/detail?option_code={option_code}&err=Gagal+memuat+paket.", status_code=303)

    try:
        res = settlement_balance(
            api_key, tokens, pctx["items"], pctx["payment_for"], False, overwrite_amount=pctx["price"]
        )
        if isinstance(res, dict) and res.get("status") == "SUCCESS":
            return RedirectResponse(url=f"/packages/detail?option_code={option_code}&msg=Pembayaran+Pulsa+berhasil+diproses!", status_code=303)
        return RedirectResponse(url=f"/packages/detail?option_code={option_code}&err=Pembayaran+Pulsa+gagal:+{json.dumps(res)}", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/packages/detail?option_code={option_code}&err=Error+pembayaran:+{str(e)}", status_code=303)


@app.post("/packages/pay/qris", response_class=HTMLResponse)
async def pay_qris_action(option_code: str = Form(...)):
    api_key, tokens = get_active_auth_ctx()
    pctx = get_payment_ctx(api_key, tokens, option_code) if api_key and tokens else None
    if not pctx:
        return RedirectResponse(url=f"/packages/detail?option_code={option_code}&err=Gagal+memuat+paket.", status_code=303)

    try:
        tx_id = settlement_qris(
            api_key, tokens, pctx["items"], pctx["payment_for"], False, overwrite_amount=pctx["price"]
        )
        if not tx_id or not isinstance(tx_id, str):
            return RedirectResponse(url=f"/packages/detail?option_code={option_code}&err=Gagal+membuat+QRIS.", status_code=303)

        qris_code = get_qris_code(api_key, tokens, tx_id)
        if qris_code:
            qris_b64 = base64.urlsafe_b64encode(str(qris_code).encode()).decode()
            qris_url = f"https://ki-ar-kod.netlify.app/?data={qris_b64}"
            return RedirectResponse(url=f"/packages/detail?option_code={option_code}&msg=QRIS+Berhasil!+Link:+{qris_url}", status_code=303)

        return RedirectResponse(url=f"/packages/detail?option_code={option_code}&msg=QRIS+Created+(ID:+{tx_id})+namun+gagal+generate+link.", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/packages/detail?option_code={option_code}&err=Error+QRIS:+{str(e)}", status_code=303)


@app.post("/packages/pay/ewallet", response_class=HTMLResponse)
async def pay_ewallet_action(option_code: str = Form(...), method: str = Form(...), wallet_number: str = Form("")):
    api_key, tokens = get_active_auth_ctx()
    pctx = get_payment_ctx(api_key, tokens, option_code) if api_key and tokens else None
    if not pctx:
        return RedirectResponse(url=f"/packages/detail?option_code={option_code}&err=Gagal+memuat+paket.", status_code=303)

    try:
        res = settlement_multipayment(
            api_key, tokens, pctx["items"], wallet_number, method, pctx["payment_for"], False, overwrite_amount=pctx["price"]
        )
        if isinstance(res, dict) and res.get("status") == "SUCCESS":
            deeplink = res.get("data", {}).get("deeplink", "")
            if deeplink:
                return RedirectResponse(url=f"/packages/detail?option_code={option_code}&msg=Berhasil!+Deeplink:+{deeplink}", status_code=303)
            return RedirectResponse(url=f"/packages/detail?option_code={option_code}&msg=Pembayaran+{method}+berhasil+dibuat.", status_code=303)
        return RedirectResponse(url=f"/packages/detail?option_code={option_code}&err=Gagal+pembayaran+{method}:+{json.dumps(res)}", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/packages/detail?option_code={option_code}&err=Error+E-Wallet:+{str(e)}", status_code=303)


@app.post("/packages/pay/decoy-balance", response_class=HTMLResponse)
async def pay_decoy_balance_action(option_code: str = Form(...), v2: int = Form(0)):
    api_key, tokens = get_active_auth_ctx()
    pctx = get_payment_ctx(api_key, tokens, option_code) if api_key and tokens else None
    if not pctx:
        return RedirectResponse(url=f"/packages/detail?option_code={option_code}&err=Gagal+memuat+paket.", status_code=303)

    try:
        decoy = DecoyInstance.get_decoy("balance")
        decoy_pkg = get_package(api_key, tokens, decoy.get("option_code", "")) if decoy else None
        if not decoy_pkg:
            return RedirectResponse(url=f"/packages/detail?option_code={option_code}&err=Gagal+memuat+decoy+package.", status_code=303)

        items = [cast(PaymentItem, pctx["items"][0])]
        items.append(cast(PaymentItem, {
            "item_code": decoy_pkg.get("package_option", {}).get("package_option_code", ""),
            "product_type": "",
            "item_price": int(decoy_pkg.get("package_option", {}).get("price", 0)),
            "item_name": decoy_pkg.get("package_option", {}).get("name", "Decoy"),
            "tax": 0,
            "token_confirmation": decoy_pkg.get("token_confirmation", ""),
        }))

        total = pctx["price"] + int(items[1]["item_price"])
        payment_for = "🤫" if v2 == 1 else pctx["payment_for"]
        token_idx = 1 if v2 == 1 else 0

        res = settlement_balance(
            api_key, tokens, items, payment_for, False, overwrite_amount=total, token_confirmation_idx=token_idx
        )
        if isinstance(res, dict) and res.get("status") == "SUCCESS":
            return RedirectResponse(url=f"/packages/detail?option_code={option_code}&msg=Pulsa+Decoy+berhasil!", status_code=303)
        return RedirectResponse(url=f"/packages/detail?option_code={option_code}&err=Pulsa+Decoy+gagal:+{json.dumps(res)}", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/packages/detail?option_code={option_code}&err=Error+Pulsa+Decoy:+{str(e)}", status_code=303)


@app.post("/packages/pay/decoy-qris", response_class=HTMLResponse)
async def pay_decoy_qris_action(option_code: str = Form(...), decoy_type: str = Form("qris")):
    api_key, tokens = get_active_auth_ctx()
    pctx = get_payment_ctx(api_key, tokens, option_code) if api_key and tokens else None
    if not pctx:
        return RedirectResponse(url=f"/packages/detail?option_code={option_code}&err=Gagal+memuat+paket.", status_code=303)

    try:
        decoy = DecoyInstance.get_decoy(decoy_type)
        decoy_pkg = get_package(api_key, tokens, decoy.get("option_code", "")) if decoy else None
        if not decoy_pkg:
            return RedirectResponse(url=f"/packages/detail?option_code={option_code}&err=Gagal+memuat+decoy+package.", status_code=303)

        items = [cast(PaymentItem, pctx["items"][0])]
        items.append(cast(PaymentItem, {
            "item_code": decoy_pkg.get("package_option", {}).get("package_option_code", ""),
            "product_type": "",
            "item_price": int(decoy_pkg.get("package_option", {}).get("price", 0)),
            "item_name": decoy_pkg.get("package_option", {}).get("name", "Decoy"),
            "tax": 0,
            "token_confirmation": decoy_pkg.get("token_confirmation", ""),
        }))

        total = pctx["price"] + int(items[1]["item_price"])
        tx_id = settlement_qris(
            api_key, tokens, items, "SHARE_PACKAGE", False, overwrite_amount=total, token_confirmation_idx=1
        )
        if not tx_id or not isinstance(tx_id, str):
            return RedirectResponse(url=f"/packages/detail?option_code={option_code}&err=Gagal+membuat+QRIS+Decoy.", status_code=303)

        qris_code = get_qris_code(api_key, tokens, tx_id)
        if qris_code:
            qris_b64 = base64.urlsafe_b64encode(str(qris_code).encode()).decode()
            qris_url = f"https://ki-ar-kod.netlify.app/?data={qris_b64}"
            return RedirectResponse(url=f"/packages/detail?option_code={option_code}&msg=QRIS+Decoy+Siap!+Link:+{qris_url}", status_code=303)
        return RedirectResponse(url=f"/packages/detail?option_code={option_code}&msg=QRIS+Decoy+Created+(ID:+{tx_id})", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/packages/detail?option_code={option_code}&err=Error+QRIS+Decoy:+{str(e)}", status_code=303)


@app.post("/packages/pay/decoy-qris-manual", response_class=HTMLResponse)
async def pay_decoy_qris_manual_action(option_code: str = Form(...), decoy_type: str = Form("qris"), amount: int = Form(...)):
    api_key, tokens = get_active_auth_ctx()
    pctx = get_payment_ctx(api_key, tokens, option_code) if api_key and tokens else None
    if not pctx:
        return RedirectResponse(url=f"/packages/detail?option_code={option_code}&err=Gagal+memuat+paket.", status_code=303)

    try:
        decoy = DecoyInstance.get_decoy(decoy_type)
        decoy_pkg = get_package(api_key, tokens, decoy.get("option_code", "")) if decoy else None
        if not decoy_pkg:
            return RedirectResponse(url=f"/packages/detail?option_code={option_code}&err=Gagal+memuat+decoy+package.", status_code=303)

        items = [cast(PaymentItem, pctx["items"][0])]
        items.append(cast(PaymentItem, {
            "item_code": decoy_pkg.get("package_option", {}).get("package_option_code", ""),
            "product_type": "",
            "item_price": int(decoy_pkg.get("package_option", {}).get("price", 0)),
            "item_name": decoy_pkg.get("package_option", {}).get("name", "Decoy"),
            "tax": 0,
            "token_confirmation": decoy_pkg.get("token_confirmation", ""),
        }))

        tx_id = settlement_qris(
            api_key, tokens, items, "SHARE_PACKAGE", False, overwrite_amount=amount, token_confirmation_idx=1
        )
        if not tx_id or not isinstance(tx_id, str):
            return RedirectResponse(url=f"/packages/detail?option_code={option_code}&err=Gagal+membuat+QRIS+Decoy+Manual.", status_code=303)

        qris_code = get_qris_code(api_key, tokens, tx_id)
        if qris_code:
            qris_b64 = base64.urlsafe_b64encode(str(qris_code).encode()).decode()
            qris_url = f"https://ki-ar-kod.netlify.app/?data={qris_b64}"
            return RedirectResponse(url=f"/packages/detail?option_code={option_code}&msg=QRIS+Decoy+Manual+Siap!+Link:+{qris_url}", status_code=303)
        return RedirectResponse(url=f"/packages/detail?option_code={option_code}&msg=QRIS+Decoy+Manual+Created+(ID:+{tx_id})", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/packages/detail?option_code={option_code}&err=Error+QRIS+Decoy+Manual:+{str(e)}", status_code=303)


@app.post("/packages/pay/balance-n", response_class=HTMLResponse)
async def pay_balance_n_action(
    option_code: str = Form(...),
    count: int = Form(1),
    delay_seconds: int = Form(0),
    use_decoy: Optional[int] = Form(None),
):
    api_key, tokens = get_active_auth_ctx()
    pctx = get_payment_ctx(api_key, tokens, option_code) if api_key and tokens else None
    if not pctx:
        return RedirectResponse(url=f"/packages/detail?option_code={option_code}&err=Gagal+memuat+paket.", status_code=303)

    ok_cnt, fail_cnt = 0, 0
    is_decoy = (use_decoy == 1)

    try:
        for i in range(count):
            if is_decoy:
                decoy = DecoyInstance.get_decoy("balance")
                decoy_pkg = get_package(api_key, tokens, decoy.get("option_code", "")) if decoy else None
                if decoy_pkg:
                    items = [cast(PaymentItem, pctx["items"][0])]
                    items.append(cast(PaymentItem, {
                        "item_code": decoy_pkg.get("package_option", {}).get("package_option_code", ""),
                        "product_type": "",
                        "item_price": int(decoy_pkg.get("package_option", {}).get("price", 0)),
                        "item_name": decoy_pkg.get("package_option", {}).get("name", "Decoy"),
                        "tax": 0,
                        "token_confirmation": decoy_pkg.get("token_confirmation", ""),
                    }))
                    total = pctx["price"] + int(items[1]["item_price"])
                    res = settlement_balance(api_key, tokens, items, pctx["payment_for"], False, overwrite_amount=total)
                else:
                    res = None
            else:
                res = settlement_balance(api_key, tokens, pctx["items"], pctx["payment_for"], False, overwrite_amount=pctx["price"])

            if isinstance(res, dict) and res.get("status") == "SUCCESS":
                ok_cnt += 1
            else:
                fail_cnt += 1

        return RedirectResponse(
            url=f"/packages/detail?option_code={option_code}&msg=Pembayaran+N+kali+selesai.+Berhasil:+{ok_cnt},+Gagal:+{fail_cnt}",
            status_code=303,
        )
    except Exception as e:
        return RedirectResponse(url=f"/packages/detail?option_code={option_code}&err=Error+Pembayaran+N+kali:+{str(e)}", status_code=303)


# ================= FAMILY PLAN (AKRAB) =================
@app.get("/famplan", response_class=HTMLResponse)
@app.get("/family-plan", response_class=HTMLResponse)
async def famplan_page(request: Request, msg: str = "", err: str = ""):
    context = get_context(request, msg=msg, err=err)
    api_key, tokens = get_active_auth_ctx()

    info = None
    if api_key and tokens:
        try:
            res = get_family_data(api_key, tokens)
            detail = res.get("data", {}) if isinstance(res, dict) else {}
            member_info = detail.get("member_info", {})
            plan_type = member_info.get("plan_type", "")
            if plan_type:
                members_formatted = []
                for m in member_info.get("members", []):
                    usage = m.get("usage", {})
                    members_formatted.append({
                        "msisdn": m.get("msisdn"),
                        "alias": m.get("alias", "N/A"),
                        "family_member_id": m.get("family_member_id"),
                        "slot_id": m.get("slot_id"),
                        "used": format_quota_byte(usage.get("quota_used", 0)),
                        "allocated": format_quota_byte(usage.get("quota_allocated", 0)),
                    })

                info = {
                    "plan_type": plan_type,
                    "parent_msisdn": member_info.get("parent_msisdn", "N/A"),
                    "total_quota": format_quota_byte(member_info.get("total_quota", 0)),
                    "remaining_quota": format_quota_byte(member_info.get("remaining_quota", 0)),
                    "members": members_formatted,
                }
        except Exception as e:
            context["err"] = f"Error memuat Family Plan: {str(e)}"

    context["info"] = info
    return render("famplan.html", context)


@app.post("/famplan/change", response_class=HTMLResponse)
async def famplan_change_action(
    slot_index: int = Form(...),
    msisdn: str = Form(...),
    parent_alias: str = Form(...),
    child_alias: str = Form(...),
):
    api_key, tokens = get_active_auth_ctx()
    if not api_key or not tokens:
        return RedirectResponse(url="/famplan?err=Belum+ada+akun+aktif.", status_code=303)

    try:
        res = get_family_data(api_key, tokens)
        members = res.get("data", {}).get("member_info", {}).get("members", [])
        if slot_index < 1 or slot_index > len(members):
            return RedirectResponse(url="/famplan?err=Slot+tidak+valid.", status_code=303)

        slot = members[slot_index - 1]
        result = change_member(api_key, tokens, parent_alias, child_alias, slot.get("slot_id"), slot.get("family_member_id"), msisdn)
        return RedirectResponse(url=f"/famplan?msg=Hasil+ganti+member:+{result.get('status', 'OK')}", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/famplan?err=Error+ganti+member:+{str(e)}", status_code=303)


@app.post("/famplan/remove", response_class=HTMLResponse)
async def famplan_remove_action(slot_index: int = Form(...)):
    api_key, tokens = get_active_auth_ctx()
    if not api_key or not tokens:
        return RedirectResponse(url="/famplan?err=Belum+ada+akun+aktif.", status_code=303)

    try:
        res = get_family_data(api_key, tokens)
        members = res.get("data", {}).get("member_info", {}).get("members", [])
        if slot_index < 1 or slot_index > len(members):
            return RedirectResponse(url="/famplan?err=Slot+tidak+valid.", status_code=303)

        slot = members[slot_index - 1]
        result = remove_member(api_key, tokens, slot.get("family_member_id"))
        return RedirectResponse(url=f"/famplan?msg=Hasil+hapus+member:+{result.get('status', 'OK')}", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/famplan?err=Error+hapus+member:+{str(e)}", status_code=303)


@app.post("/famplan/limit", response_class=HTMLResponse)
async def famplan_limit_action(slot_index: int = Form(...), mb: int = Form(...)):
    api_key, tokens = get_active_auth_ctx()
    if not api_key or not tokens:
        return RedirectResponse(url="/famplan?err=Belum+ada+akun+aktif.", status_code=303)

    try:
        res = get_family_data(api_key, tokens)
        members = res.get("data", {}).get("member_info", {}).get("members", [])
        if slot_index < 1 or slot_index > len(members):
            return RedirectResponse(url="/famplan?err=Slot+tidak+valid.", status_code=303)

        slot = members[slot_index - 1]
        result = set_quota_limit(api_key, tokens, slot.get("usage", {}).get("quota_allocated", 0), mb * 1024 * 1024, slot.get("family_member_id"))
        return RedirectResponse(url=f"/famplan?msg=Limit+berhasil+di-set+ke+{mb}+MB", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/famplan?err=Error+set+limit:+{str(e)}", status_code=303)


# ================= CIRCLE =================
@app.get("/circle", response_class=HTMLResponse)
async def circle_page(request: Request, msg: str = "", err: str = ""):
    context = get_context(request, msg=msg, err=err)
    api_key, tokens = get_active_auth_ctx()

    circle_data = None
    bonuses_formatted = []
    if api_key and tokens:
        try:
            grp = get_group_data(api_key, tokens)
            data = grp.get("data", {}) if isinstance(grp, dict) else {}
            group_id = data.get("group_id", "")
            if group_id:
                members_res = get_group_members(api_key, tokens, group_id)
                members = members_res.get("data", {}).get("members", []) if isinstance(members_res, dict) else []

                parent_subs_id = ""
                for m in members:
                    if m.get("member_role") == "PARENT":
                        parent_subs_id = m.get("subscriber_number", "")
                        break

                spend = spending_tracker(api_key, tokens, parent_subs_id, group_id).get("data", {}) if parent_subs_id else {}
                members_formatted = []
                for m in members:
                    msisdn = decrypt_circle_msisdn(api_key, m.get("msisdn", ""))
                    members_formatted.append({
                        "member_id": m.get("member_id", ""),
                        "member_name": m.get("member_name", "N/A"),
                        "member_role": m.get("member_role", "N/A"),
                        "msisdn": msisdn or "<No Number>",
                    })

                circle_data = {
                    "group_id": group_id,
                    "group_name": data.get("group_name", "N/A"),
                    "group_status": data.get("group_status", "N/A"),
                    "owner_name": data.get("owner_name", "N/A"),
                    "spend": spend.get("spend", 0),
                    "target": spend.get("target", 0),
                    "members": members_formatted,
                }

                bonus_res = get_bonus_data(api_key, tokens, parent_subs_id, group_id) if parent_subs_id else {}
                for b in bonus_res.get("data", {}).get("bonuses", []) if isinstance(bonus_res, dict) else []:
                    bonuses_formatted.append({
                        "name": b.get("name", "N/A"),
                        "bonus_type": b.get("bonus_type", "N/A"),
                        "action_type": b.get("action_type", "N/A"),
                    })
        except Exception as e:
            context["err"] = f"Error memuat Circle: {str(e)}"

    context["circle"] = circle_data
    context["bonuses"] = bonuses_formatted
    return render("circle.html", context)


@app.post("/circle/invite", response_class=HTMLResponse)
async def circle_invite_action(msisdn: str = Form(...), name: str = Form(...)):
    api_key, tokens = get_active_auth_ctx()
    if not api_key or not tokens:
        return RedirectResponse(url="/circle?err=Belum+ada+akun+aktif.", status_code=303)

    try:
        grp = get_group_data(api_key, tokens)
        data = grp.get("data", {}) if isinstance(grp, dict) else {}
        group_id = data.get("group_id", "")
        if not group_id:
            return RedirectResponse(url="/circle?err=Tidak+tergabung+dalam+Circle.", status_code=303)

        members_res = get_group_members(api_key, tokens, group_id)
        members = members_res.get("data", {}).get("members", []) if isinstance(members_res, dict) else []
        parent_member_id = next((m.get("member_id", "") for m in members if m.get("member_role") == "PARENT"), "")

        res = invite_circle_member(api_key, tokens, msisdn, name, group_id, parent_member_id)
        return RedirectResponse(url=f"/circle?msg=Hasil+undangan:+{res.get('status', 'OK')}", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/circle?err=Error+invite+circle:+{str(e)}", status_code=303)


@app.post("/circle/accept", response_class=HTMLResponse)
async def circle_accept_action(member_index: int = Form(...)):
    api_key, tokens = get_active_auth_ctx()
    if not api_key or not tokens:
        return RedirectResponse(url="/circle?err=Belum+ada+akun+aktif.", status_code=303)

    try:
        grp = get_group_data(api_key, tokens)
        group_id = grp.get("data", {}).get("group_id", "")
        members = get_group_members(api_key, tokens, group_id).get("data", {}).get("members", [])
        if member_index < 1 or member_index > len(members):
            return RedirectResponse(url="/circle?err=Index+member+tidak+valid.", status_code=303)

        member = members[member_index - 1]
        res = accept_circle_invitation(api_key, tokens, group_id, member.get("member_id", ""))
        return RedirectResponse(url=f"/circle?msg=Hasil+accept:+{res.get('status', 'OK')}", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/circle?err=Error+accept+circle:+{str(e)}", status_code=303)


@app.post("/circle/remove", response_class=HTMLResponse)
async def circle_remove_action(member_index: int = Form(...)):
    api_key, tokens = get_active_auth_ctx()
    if not api_key or not tokens:
        return RedirectResponse(url="/circle?err=Belum+ada+akun+aktif.", status_code=303)

    try:
        grp = get_group_data(api_key, tokens)
        group_id = grp.get("data", {}).get("group_id", "")
        members = get_group_members(api_key, tokens, group_id).get("data", {}).get("members", [])
        parent_member_id = next((m.get("member_id", "") for m in members if m.get("member_role") == "PARENT"), "")
        if member_index < 1 or member_index > len(members):
            return RedirectResponse(url="/circle?err=Index+member+tidak+valid.", status_code=303)

        member = members[member_index - 1]
        res = remove_circle_member(api_key, tokens, member.get("member_id", ""), group_id, parent_member_id, False)
        return RedirectResponse(url=f"/circle?msg=Hasil+remove:+{res.get('status', 'OK')}", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/circle?err=Error+remove+circle:+{str(e)}", status_code=303)


# ================= STORE =================
@app.get("/store/segments", response_class=HTMLResponse)
async def store_segments_page(request: Request, msg: str = "", err: str = ""):
    context = get_context(request, msg=msg, err=err)
    context["title"] = "🏪 Store Segments"
    context["active_tab"] = "segments"
    api_key, tokens = get_active_auth_ctx()
    items = []
    if api_key and tokens:
        try:
            res = get_segments(api_key, tokens, False)
            if isinstance(res, dict):
                for seg in res.get("data", {}).get("store_segments", []):
                    seg_title = seg.get("title", "N/A")
                    for banner in seg.get("banners", []):
                        items.append({
                            "label": f"[{seg_title}] {banner.get('family_name', 'N/A')} - {banner.get('title', 'N/A')} (Rp {banner.get('discounted_price', 'N/A')})",
                            "action_type": banner.get("action_type", ""),
                            "action_param": banner.get("action_param", ""),
                        })
        except Exception as e:
            context["err"] = f"Error store segments: {str(e)}"
    context["items"] = items
    return render("store.html", context)


@app.get("/store/families", response_class=HTMLResponse)
async def store_families_page(request: Request, msg: str = "", err: str = ""):
    context = get_context(request, msg=msg, err=err)
    context["title"] = "🧬 Store Families"
    context["active_tab"] = "families"
    api_key, tokens = get_active_auth_ctx()
    active_user = context.get("active_user") or {}
    items = []
    if api_key and tokens:
        try:
            res = get_family_list(api_key, tokens, active_user.get("subscription_type", "PREPAID"), False)
            if isinstance(res, dict):
                for fam in res.get("data", {}).get("results", []):
                    items.append({
                        "label": fam.get("label", "N/A"),
                        "family_code": fam.get("id", ""),
                    })
        except Exception as e:
            context["err"] = f"Error store families: {str(e)}"
    context["items"] = items
    return render("store.html", context)


@app.get("/store/packages", response_class=HTMLResponse)
async def store_packages_page(request: Request, msg: str = "", err: str = ""):
    context = get_context(request, msg=msg, err=err)
    context["title"] = "🛒 Store Packages"
    context["active_tab"] = "packages"
    api_key, tokens = get_active_auth_ctx()
    active_user = context.get("active_user") or {}
    items = []
    if api_key and tokens:
        try:
            res = get_store_packages(api_key, tokens, active_user.get("subscription_type", "PREPAID"), False)
            if isinstance(res, dict):
                for pkg in res.get("data", {}).get("results_price_only", []):
                    price = pkg.get("discounted_price", 0) or pkg.get("original_price", 0)
                    items.append({
                        "label": f"{pkg.get('title', 'N/A')} | {pkg.get('family_name', 'N/A')} | Rp {price}",
                        "action_type": pkg.get("action_type", ""),
                    })
        except Exception as e:
            context["err"] = f"Error store packages: {str(e)}"
    context["items"] = items
    return render("store.html", context)


@app.get("/store/redeemables", response_class=HTMLResponse)
@app.get("/store/redemables", response_class=HTMLResponse)
async def store_redeemables_page(request: Request, msg: str = "", err: str = ""):
    context = get_context(request, msg=msg, err=err)
    context["title"] = "🎟️ Redeemables"
    context["active_tab"] = "redeemables"
    api_key, tokens = get_active_auth_ctx()
    items = []
    if api_key and tokens:
        try:
            res = get_redeemables(api_key, tokens, False)
            if isinstance(res, dict):
                for cat in res.get("data", {}).get("categories", []):
                    cat_name = cat.get("category_name", "N/A")
                    for item in cat.get("redeemables", []):
                        items.append({
                            "label": f"[{cat_name}] {item.get('name', 'N/A')}",
                            "action_type": item.get("action_type", ""),
                        })
        except Exception as e:
            context["err"] = f"Error redeemables: {str(e)}"
    context["items"] = items
    return render("store.html", context)


# ================= HISTORY & NOTIFICATIONS =================
@app.get("/history", response_class=HTMLResponse)
@app.get("/transactions", response_class=HTMLResponse)
async def history_page(request: Request, msg: str = "", err: str = ""):
    context = get_context(request, msg=msg, err=err)
    api_key, tokens = get_active_auth_ctx()
    history = []
    if api_key and tokens:
        try:
            data = get_transaction_history(api_key, tokens)
            if isinstance(data, dict):
                history = data.get("list", [])
        except Exception as e:
            context["err"] = f"Error memuat riwayat: {str(e)}"
    context["history"] = history
    return render("history.html", context)


@app.get("/notifications", response_class=HTMLResponse)
async def notifications_page(request: Request, msg: str = "", err: str = ""):
    context = get_context(request, msg=msg, err=err)
    api_key, tokens = get_active_auth_ctx()
    notifications = []
    if api_key and tokens:
        try:
            data = dashboard_segments(api_key, tokens)
            if isinstance(data, dict):
                notifications = data.get("data", {}).get("notification", {}).get("data", [])
        except Exception as e:
            context["err"] = f"Error memuat notifikasi: {str(e)}"
    context["notifications"] = notifications
    return render("notifications.html", context)


@app.post("/notifications/mark-all", response_class=HTMLResponse)
async def mark_all_notifications_action():
    api_key, tokens = get_active_auth_ctx()
    if api_key and tokens:
        try:
            data = dashboard_segments(api_key, tokens)
            if isinstance(data, dict):
                for item in data.get("data", {}).get("notification", {}).get("data", []):
                    if not item.get("is_read") and item.get("notification_id"):
                        get_notification_detail(api_key, tokens, item.get("notification_id"))
        except Exception:
            pass
    return RedirectResponse(url="/notifications?msg=Semua+notifikasi+telah+ditandai+dibaca.", status_code=303)


# ================= BOOKMARKS =================
@app.get("/bookmarks", response_class=HTMLResponse)
@app.get("/bookmark", response_class=HTMLResponse)
async def bookmarks_page(request: Request, msg: str = "", err: str = ""):
    context = get_context(request, msg=msg, err=err)
    try:
        context["bookmarks"] = BookmarkInstance.get_bookmarks()
    except Exception:
        context["bookmarks"] = []
    return render("bookmarks.html", context)


@app.post("/bookmarks/add", response_class=HTMLResponse)
async def add_bookmark_action(
    family_code: str = Form(...),
    variant_name: str = Form(...),
    option_name: str = Form(...),
    order: int = Form(1),
    is_enterprise: int = Form(0),
):
    api_key, tokens = get_active_auth_ctx()
    family_name = ""
    if api_key and tokens:
        try:
            family = get_family(api_key, tokens, family_code, is_enterprise == 1)
            if family:
                family_name = family.get("package_family", {}).get("name", "")
        except Exception:
            pass

    try:
        ok = BookmarkInstance.add_bookmark(
            family_code=family_code,
            family_name=family_name,
            is_enterprise=is_enterprise == 1,
            variant_name=variant_name,
            option_name=option_name,
            order=order,
        )
        if ok:
            return RedirectResponse(url="/bookmarks?msg=Bookmark+berhasil+ditambahkan.", status_code=303)
        return RedirectResponse(url="/bookmarks?err=Bookmark+sudah+ada.", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/bookmarks?err=Gagal+tambah+bookmark:+{str(e)}", status_code=303)


@app.post("/bookmarks/delete", response_class=HTMLResponse)
async def delete_bookmark_action(index: int = Form(...)):
    try:
        bookmarks = BookmarkInstance.get_bookmarks()
        if 1 <= index <= len(bookmarks):
            b = bookmarks[index - 1]
            BookmarkInstance.remove_bookmark(
                b.get("family_code", ""), bool(b.get("is_enterprise", False)), b.get("variant_name", ""), int(b.get("order", 0))
            )
            return RedirectResponse(url="/bookmarks?msg=Bookmark+berhasil+dihapus.", status_code=303)
        return RedirectResponse(url="/bookmarks?err=Index+bookmark+tidak+valid.", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/bookmarks?err=Gagal+hapus+bookmark:+{str(e)}", status_code=303)


# ================= DUKCAPIL REGISTER & VALIDATE =================
@app.get("/dukcapil", response_class=HTMLResponse)
@app.get("/register", response_class=HTMLResponse)
async def dukcapil_page(request: Request, msg: str = "", err: str = ""):
    context = get_context(request, msg=msg, err=err)
    context["result"] = ""
    return render("dukcapil.html", context)


@app.post("/dukcapil", response_class=HTMLResponse)
async def dukcapil_action(request: Request, msisdn: str = Form(...), nik: str = Form(...), kk: str = Form(...)):
    context = get_context(request)
    try:
        res = dukcapil(AuthInstance.api_key, msisdn, kk, nik)
        context["result"] = json.dumps(res, indent=2)
    except Exception as e:
        context["err"] = f"Error dukcapil: {str(e)}"
        context["result"] = ""
    return render("dukcapil.html", context)


@app.get("/validate", response_class=HTMLResponse)
@app.get("/validate-msisdn", response_class=HTMLResponse)
async def validate_page(request: Request, msg: str = "", err: str = ""):
    context = get_context(request, msg=msg, err=err)
    context["result"] = ""
    return render("validate.html", context)


@app.post("/validate", response_class=HTMLResponse)
async def validate_action(request: Request, msisdn: str = Form(...)):
    context = get_context(request)
    api_key, tokens = get_active_auth_ctx()
    if not api_key or not tokens:
        context["err"] = "Belum ada akun aktif untuk melakukan validasi."
        context["result"] = ""
    else:
        try:
            res = validate_msisdn(api_key, tokens, msisdn)
            context["result"] = json.dumps(res, indent=2)
        except Exception as e:
            context["err"] = f"Error validasi: {str(e)}"
            context["result"] = ""
    return render("validate.html", context)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web_main:app", host="0.0.0.0", port=5000, reload=True)
