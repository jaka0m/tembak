# -*- coding: utf-8 -*-
from dotenv import load_dotenv

from app.service.git import check_for_updates
load_dotenv()

import sys, json
from datetime import datetime
from app.menus.util import clear_screen, pause
from app.client.engsel import (
    get_balance,
    get_tiering_info,
)
from app.client.famplan import validate_msisdn
from app.menus.payment import show_transaction_history
from app.service.auth import AuthInstance
from app.menus.bookmark import show_bookmark_menu
from app.menus.account import show_account_menu
from app.menus.package import fetch_my_packages, get_packages_by_family, show_package_details
from app.menus.hot import show_hot_menu, show_hot_menu2
from app.service.sentry import enter_sentry_mode
from app.menus.purchase import purchase_by_family
from app.menus.famplan import show_family_info
from app.menus.circle import show_circle_info
from app.menus.notification import show_notification_menu
from app.menus.store.segments import show_store_segments_menu
from app.menus.store.search import show_family_list_menu, show_store_packages_menu
from app.menus.store.redemables import show_redeemables_menu
from app.client.registration import dukcapil

WIDTH = 55

# =========================
# HACKER / CYBER TERMINAL UI
# =========================
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[92m"
CYAN = "\033[96m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
YELLOW = "\033[93m"
RED = "\033[91m"
WHITE = "\033[97m"
GRAY = "\033[90m"

def _term(text, color=GREEN, bold=False):
    style = BOLD if bold else ""
    return f"{style}{color}{text}{RESET}"

def _line(char="=", width=WIDTH):
    return _term(char * width, CYAN)

def _panel(title, rows=None):
    print(_line("="))
    print(_term(f"  ##. {title.upper()} .##", MAGENTA, True))
    print(_line("-"))
    if rows:
        for row in rows:
            print(f"  {_term(row, WHITE)}")
    print(_line("="))

def _menu_item(key, label):
    print(f"  {_term(f'[{key:>2}]', CYAN, True)} {_term(label, WHITE)}")

def _prompt(text):
    return input(f"\n  {_term('+-[', GREEN)}{_term('CYBER-SHELL', CYAN, True)}{_term(']->', GREEN)} {_term(text, WHITE)} ")

def _status(label, value, color=GREEN):
    print(f"  {_term(label + ':', GRAY)} {_term(str(value), color, True)}")

def show_main_menu(profile):
    clear_screen()

    expired_at_dt = datetime.fromtimestamp(
        profile["balance_expired_at"]
    ).strftime("%Y-%m-%d")

    # Header / banner
    print()
    print(_term("+" + "=" * (WIDTH - 2) + "+", GREEN, True))
    banner = [
        "##+  ##+ #####+  ######+##+  ##+",
        "##|  ##|##+==##+##+====+##| ##++",
        "#######|#######|##|     #####++ ",
        "##+==##|##+==##|##|     ##+=##+ ",
        "##|  ##|##|  ##|+######+##|  ##+",
        "+=+  +=++=+  +=+ +=====++=+  +=+",
    ]
    for row in banner:
        print(_term("|" + row.center(WIDTH - 2) + "|", GREEN, True))
    print(_term("|" + "SECURE TERMINAL // CONTROL PANEL".center(WIDTH - 2) + "|", CYAN, True))
    print(_term("+" + "=" * (WIDTH - 2) + "+", GREEN, True))
    print()

    # Account status
    _panel("SYSTEM STATUS", [
        f"USER       : {profile['number']}",
        f"TYPE       : {profile['subscription_type']}",
        f"BALANCE    : Rp {profile['balance']}",
        f"EXPIRES    : {expired_at_dt}",
        f"{profile['point_info']}",
        "STATUS     : ONLINE / AUTHENTICATED",
    ])

    print()
    print(_term("  +-[ MAIN COMMAND MATRIX ]", MAGENTA, True))
    print(_term("  ++---------------------------------------------------", MAGENTA))

    _menu_item("1", "Login / Ganti akun")
    _menu_item("2", "Lihat Paket Saya")
    _menu_item("3", "Beli Paket HOT")
    _menu_item("4", "Beli Paket HOT-2")
    _menu_item("5", "Beli Paket berdasarkan Option Code")
    _menu_item("6", "Beli Paket berdasarkan Family Code")
    _menu_item("7", "Beli Semua Paket di Family Code (loop)")
    _menu_item("8", "Riwayat Transaksi")
    _menu_item("9", "Family Plan / Akrab Organizer")
    _menu_item("10", "Circle")
    _menu_item("11", "Store Segments")
    _menu_item("12", "Store Family List")
    _menu_item("13", "Store Packages")
    _menu_item("14", "Redeemables")
    _menu_item("R", "Register")
    _menu_item("N", "Notifikasi")
    _menu_item("V", "Validate MSISDN")
    _menu_item("00", "Bookmark Paket")
    _menu_item("S", "Sentry Mode")
    _menu_item("99", "Tutup aplikasi")

    print()
    print(_line("-"))
    print(f"  {_term('TIP', YELLOW, True)} {_term('Gunakan 99 untuk keluar - CTRL+C untuk emergency exit', GRAY)}")
    print(_line("-"))

show_menu = True
def main():
    
    while True:
        active_user = AuthInstance.get_active_user()

        # Logged in
        if active_user is not None:
            balance = get_balance(AuthInstance.api_key, active_user["tokens"]["id_token"])
            balance_remaining = balance.get("remaining")
            balance_expired_at = balance.get("expired_at")
            
            point_info = "Points: N/A | Tier: N/A"
            
            if active_user["subscription_type"] == "PREPAID":
                tiering_data = get_tiering_info(AuthInstance.api_key, active_user["tokens"])
                tier = tiering_data.get("tier", 0)
                current_point = tiering_data.get("current_point", 0)
                point_info = f"Points: {current_point} | Tier: {tier}"
            
            profile = {
                "number": active_user["number"],
                "subscriber_id": active_user["subscriber_id"],
                "subscription_type": active_user["subscription_type"],
                "balance": balance_remaining,
                "balance_expired_at": balance_expired_at,
                "point_info": point_info
            }

            show_main_menu(profile)

            choice = _prompt("Pilih command")
            # Testing shortcuts
            if choice.lower() == "t":
                pause()
            elif choice == "1":
                selected_user_number = show_account_menu()
                if selected_user_number:
                    AuthInstance.set_active_user(selected_user_number)
                else:
                    print(_term("  [!] No user selected or failed to load user.", RED, True))
                continue
            elif choice == "2":
                fetch_my_packages()
                continue
            elif choice == "3":
                show_hot_menu()
            elif choice == "4":
                show_hot_menu2()
            elif choice == "5":
                option_code = _prompt("Enter option code (99 = cancel)")
                if option_code == "99":
                    continue
                show_package_details(
                    AuthInstance.api_key,
                    active_user["tokens"],
                    option_code,
                    False
                )
            elif choice == "6":
                family_code = _prompt("Enter family code (99 = cancel)")
                if family_code == "99":
                    continue
                get_packages_by_family(family_code)
            elif choice == "7":
                family_code = _prompt("Enter family code (99 = cancel)")
                if family_code == "99":
                    continue

                start_from_option = _prompt("Start option number (default 1)")
                try:
                    start_from_option = int(start_from_option)
                except ValueError:
                    start_from_option = 1

                use_decoy = _prompt("Use decoy package? (y/n)").lower() == 'y'
                pause_on_success = _prompt("Pause after successful purchase? (y/n)").lower() == 'y'
                delay_seconds = _prompt("Delay seconds between purchases (0 = no delay)")
                try:
                    delay_seconds = int(delay_seconds)
                except ValueError:
                    delay_seconds = 0
                purchase_by_family(
                    family_code,
                    use_decoy,
                    pause_on_success,
                    delay_seconds,
                    start_from_option
                )
            elif choice == "8":
                show_transaction_history(AuthInstance.api_key, active_user["tokens"])
            elif choice == "9":
                show_family_info(AuthInstance.api_key, active_user["tokens"])
            elif choice == "10":
                show_circle_info(AuthInstance.api_key, active_user["tokens"])
            elif choice == "11":
                input_11 = _prompt("Enterprise store? (y/n)").lower()
                is_enterprise = input_11 == 'y'
                show_store_segments_menu(is_enterprise)
            elif choice == "12":
                input_12_1 = _prompt("Enterprise? (y/n)").lower()
                is_enterprise = input_12_1 == 'y'
                show_family_list_menu(profile['subscription_type'], is_enterprise)
            elif choice == "13":
                input_13_1 = _prompt("Enterprise? (y/n)").lower()
                is_enterprise = input_13_1 == 'y'
                
                show_store_packages_menu(profile['subscription_type'], is_enterprise)
            elif choice == "14":
                input_14_1 = _prompt("Enterprise? (y/n)").lower()
                is_enterprise = input_14_1 == 'y'
                
                show_redeemables_menu(is_enterprise)
            elif choice == "00":
                show_bookmark_menu()
            elif choice == "99":
                print(_term("\n  [SYSTEM] Connection terminated. Goodbye.", GREEN, True))
                sys.exit(0)
            elif choice.lower() == "r":
                msisdn = _prompt("Enter MSISDN (628xxxx)")
                nik = _prompt("Enter NIK")
                kk = _prompt("Enter KK")
                
                res = dukcapil(
                    AuthInstance.api_key,
                    msisdn,
                    kk,
                    nik,
                )
                print(json.dumps(res, indent=2))
                pause()
            elif choice.lower() == "v":
                msisdn = _prompt("MSISDN to validate (628xxxx)")
                res = validate_msisdn(
                    AuthInstance.api_key,
                    active_user["tokens"],
                    msisdn,
                )
                print(json.dumps(res, indent=2))
                pause()
            elif choice.lower() == "n":
                show_notification_menu()
            elif choice == "s":
                enter_sentry_mode()
            else:
                print(_term("  [!] Invalid command. Please try again.", RED, True))
                pause()
        else:
            # Not logged in
            selected_user_number = show_account_menu()
            if selected_user_number:
                AuthInstance.set_active_user(selected_user_number)
            else:
                print(_term("  [!] No user selected or failed to load user.", RED, True))

if __name__ == "__main__":
    try:
        clear_screen()
        print()
        print(_term("+" + "=" * (WIDTH - 2) + "+", GREEN, True))
        print(_term("|" + " CYBER TERMINAL // INITIALIZING ".center(WIDTH - 2) + "|", CYAN, True))
        print(_term("+" + "=" * (WIDTH - 2) + "+", GREEN, True))
        print()
        print(_term("  [BOOT] Checking for updates...", CYAN, True))
        need_update = check_for_updates()
        if need_update:
            pause()

        main()
    except KeyboardInterrupt:
        print("\nExiting the application.")
    # except Exception as e:
    #     print(f"An error occurred: {e}")