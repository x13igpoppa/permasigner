import os
from pathlib import Path
from shutil import copy, copytree
import plistlib
import requests
from urllib.parse import urlparse
import zipfile
import sys
import subprocess
import tempfile
import platform
import argparse
from glob import glob
import time
from subprocess import PIPE, DEVNULL
from getpass import getpass

from utils.copy import Copy
from utils.downloader import DpkgDeb, Ldid
from utils.hash import LdidHash
from utils.installer import Installer

if not (sys.platform == "darwin" and platform.machine().startswith("i")):
    from utils.usbmux import USBMux
    from paramiko.client import AutoAddPolicy, SSHClient
    from paramiko.ssh_exception import AuthenticationException, SSHException, NoValidConnectionsError
    from scp import SCPClient

""" Functions """


def cmd_in_path(args, cmd):
    if args.debug:
        print(f"[DEBUG] Checking if command {cmd} is in PATH...")

    if cmd == "ldid":
        if is_ios():
            if args.debug:
                print(f"[DEBUG] Checking for ldid on iOS")

            if is_dpkg_installed("ldid"):
                if args.debug:
                    print(f"[DEBUG] ldid is installed via dpkg")

                return True
            else:
                print(
                    "[-] ldid is required on iOS, but it is not installed. Please install it from Procursus.")
                exit(1)

        if args.debug:
            print(f"[DEBUG] Checking ldid output...")

        ldid_out = subprocess.getoutput('ldid')
        if "procursus" not in ldid_out:
            if args.debug:
                print(f"[DEBUG] ldid installed is not from Procursus")

            return False
        else:
            if args.debug:
                print(f"[DEBUG] ldid installed is from Procursus!")

            return True

    return subprocess.getstatusoutput(f"which {cmd}")[0] == 0


def is_macos():
    if platform.machine().startswith("i"):
        return False

    return sys.platform == "darwin"


def is_linux():
    return sys.platform == "linux"


def is_ios():
    if not sys.platform == "darwin":
        return False

    return platform.machine().startswith("i")


def is_dpkg_installed(pkg):
    return (os.system("dpkg -s " + pkg + "> /dev/null 2>&1")) == 0


""" Main Function """


def main(args):
    print(
        f"IPA Permasigner | Version {subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD']).decode('ascii').strip()}-{subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode('ascii').strip()}")
    print("Program created by Nebula | Original scripts created by zhuowei | CoreTrust bypass by Linus Henze")
    print()

    # Check if script is running on Windows, if so, fail
    if sys.platform == "windows":
        print("[-] Script must be ran on macOS or Linux.")
        exit(1)

    # Check if codesign is added on Linux
    if args.codesign:
        if is_linux():
            print(
                "[-] You cannot use codesign on Linux, remove the argument and it'll use ldid instead.")
            exit(1)

    ldid_in_path = cmd_in_path(args, 'ldid')
    dpkg_in_path = cmd_in_path(args, 'dpkg-deb')

    # Auto download ldid
    if not ldid_in_path:
        if Path(f"{os.getcwd()}/ldid").exists():
            if is_linux() and platform.machine() == "x86_64":
                if args.debug:
                    print(f"[DEBUG] On Linux x86_64, ldid not found...")

                if not LdidHash.check_linux_64(args):
                    print(
                        "[*] ldid is outdated or malformed, downloading latest version...")
                    os.remove(f"{os.getcwd()}/ldid")
                    Ldid.download_linux_64(args)
            elif is_linux() and platform.machine() == "aarch64":
                if args.debug:
                    print(f"[DEBUG] On Linux aarch64, ldid not found...")

                if not LdidHash.check_linux_arm64(args):
                    print(
                        "[*] ldid is outdated or malformed, downloading latest version...")
                    os.remove(f"{os.getcwd()}/ldid")
                    Ldid.download_linux_arm64(args)
            elif is_macos() and platform.machine() == "x86_64":
                if args.debug:
                    print(f"[DEBUG] On macOS x86_64, ldid not found...")

                if not LdidHash.check_macos_64(args):
                    print(
                        "[*] ldid is outdated or malformed, downloading latest version...")
                    os.remove(f"{os.getcwd()}/ldid")
                    Ldid.download_macos_64(args)
            elif is_macos() and platform.machine() == "arm64":
                if args.debug:
                    print(f"[DEBUG] On macOS arm64, ldid not found...")

                if not LdidHash.check_macos_arm64(args):
                    print(
                        "[*] ldid is outdated or malformed, downloading latest version...")
                    os.remove(f"{os.getcwd()}/ldid")
                    Ldid.download_macos_arm64(args)
        else:
            print(
                "[*] ldid not found, not from Procursus, or not up to date, downloading latest binary.")
            if is_linux() and platform.machine() == "x86_64":
                Ldid.download_linux_64(args)
            elif is_linux() and platform.machine() == "aarch64":
                Ldid.download_linux_arm64(args)
            elif is_macos() and platform.machine() == "x86_64":
                Ldid.download_macos_64(args)
            elif is_macos() and platform.machine() == "arm64":
                Ldid.download_macos_arm64(args)

    # Auto download dpkg-deb on Linux
    if not dpkg_in_path and is_linux():
        if not Path(f"{os.getcwd()}/dpkg-deb").exists():
            if platform.machine() == "x86_64":
                if args.debug:
                    print(f"[DEBUG] On Linux x86_64, dpkg-deb not found...")

                print("[*] dpkg-deb not found, downloading.")
                DpkgDeb.download_linux_64(args)
                print()
            elif platform.machine() == "aarch64":
                if args.debug:
                    print(f"[DEBUG] On Linux aarch64, dpkg-deb not found...")

                print("[*] dpkg-deb not found, downloading.")
                DpkgDeb.download_linux_arm64(args)
                print()

    if is_macos():
        if not subprocess.getstatusoutput("which dpkg")[0] == 0:
            if args.debug:
                print(f"[DEBUG] On macOS x86_64, dpkg not found...")
            print(
                "[-] dpkg is not installed and is required on macOS. Install it though brew or Procursus to continue.")
            exit(1)

    # Prompt the user if they'd like to use an external IPA or a local IPA
    if not (args.url or args.path):
        option = input(
            "[?] Would you like to use an external or a local IPA? [E, L] ")

    with tempfile.TemporaryDirectory() as tmpfolder:
        print("[*] Created temporary directory.")
        print()

        # If the user's choice is external, download an IPA
        # Otherwise, copy the IPA to the temporary directory
        if args.url:
            url = args.url

            if not os.path.splitext(urlparse(url).path)[1] == ".ipa":
                print(
                    "[-] URL provided is not an IPA, make sure to provide a direct link.")
                exit(1)

            res = requests.get(url, stream=True)

            try:
                if res.status_code == 200:
                    print(f"[*] Downloading file...")

                    with open(f"{tmpfolder}/app.ipa", "wb") as f:
                        f.write(res.content)
                else:
                    print(
                        f"[-] URL provided is not reachable. Status code: {res.status_code}")
                    exit(1)
            except requests.exceptions.RequestException as err:
                print(f"[-] URL provided is not reachable. Error: {err}")
                exit(1)
        elif args.path:
            path = args.path
            path = path.strip().lstrip("'").rstrip("'")

            if Path(path).exists():
                copy(path, f"{tmpfolder}/app.ipa")
            else:
                print(
                    "[-] That file does not exist! Make sure you're using a direct path to the IPA file.")
                exit(1)
        elif option == "E":
            url = input("[?] Paste in the *direct* path to an IPA online: ")

            if not os.path.splitext(urlparse(url).path)[1] == ".ipa":
                print(
                    "[-] URL provided is not an IPA, make sure to provide a direct link.")
                exit(1)

            res = requests.get(url, stream=True)

            try:
                if res.status_code == 200:
                    print(f"[*] Downloading file...")

                    with open(f"{tmpfolder}/app.ipa", "wb") as f:
                        f.write(res.content)
                else:
                    print(
                        f"[-] URL provided is not reachable. Status code: {res.status_code}")
                    exit(1)
            except requests.exceptions.RequestException as err:
                print(f"[-] URL provided is not reachable. Error: {err}")
                exit(1)
        elif option == "L":
            path = input(
                "[?] Paste in the path to an IPA in your file system: ")
            path = path.strip().lstrip("'").rstrip("'")

            if Path(path).exists():
                copy(path, f"{tmpfolder}/app.ipa")
            else:
                print(
                    "[-] That file does not exist! Make sure you're using a direct path to the IPA file.")
                exit(1)
        else:
            print("[-] That is not a valid option!")
            exit(1)
        print()

        # Unzip the IPA file
        print("[*] Unzipping IPA...")
        with zipfile.ZipFile(f"{tmpfolder}/app.ipa", 'r') as f:
            os.makedirs(f"{tmpfolder}/app", exist_ok=False)
            f.extractall(f"{tmpfolder}/app")
        print()

        # Read data from the plist
        print("[*] Reading plist...")

        if Path(f"{tmpfolder}/app/Payload").exists():
            for fname in os.listdir(path=f"{tmpfolder}/app/Payload"):
                if fname.endswith(".app"):
                    app_dir = fname
            print("Found app directory!")
        else:
            print("[-] IPA is not valid!")
            exit(1)

        pre_app_path = os.path.join(f"{tmpfolder}/app/Payload", app_dir)

        if Path(f'{pre_app_path}/Info.plist').exists():
            print("Found Info.plist")
            with open(f'{pre_app_path}/Info.plist', 'rb') as f:
                info = plistlib.load(f)
                app_name = info["CFBundleName"]
                app_bundle = info["CFBundleIdentifier"]
                app_version = info["CFBundleShortVersionString"]
                app_min_ios = info["MinimumOSVersion"]
                app_author = app_bundle.split(".")[1]
                if info["CFBundleExecutable"]:
                    app_executable = info["CFBundleExecutable"]
                    print("Executable found.")
                else:
                    app_executable = None
                    print("No executable found.")
                print("Found information about the app!")
        print()

        # Get the deb file ready
        print("[*] Preparing deb file...")
        print("Making directories...")
        os.makedirs(f"{tmpfolder}/deb/Applications", exist_ok=False)
        os.makedirs(f"{tmpfolder}/deb/DEBIAN", exist_ok=False)
        print("Copying deb file scripts and control...")
        Copy.copy_postrm(f"{tmpfolder}/deb/DEBIAN/postrm", app_name)
        Copy.copy_postinst(f"{tmpfolder}/deb/DEBIAN/postinst", app_name)
        Copy.copy_control(f"{tmpfolder}/deb/DEBIAN/control", app_name,
                          app_bundle, app_version, app_min_ios, app_author)
        print("Copying app files...")
        full_app_path = os.path.join(f"{tmpfolder}/deb/Applications", app_dir)
        copytree(pre_app_path, full_app_path)
        print("Changing deb file scripts permissions...")
        subprocess.run(
            f"chmod 0755 {tmpfolder}/deb/DEBIAN/postrm".split(), stdout=subprocess.DEVNULL)
        subprocess.run(
            f"chmod 0755 {tmpfolder}/deb/DEBIAN/postinst".split(), stdout=subprocess.DEVNULL)
        if app_executable is not None:
            print("Changing app executable permissions...")
            exec_path = os.path.join(full_app_path, app_executable)
            subprocess.run(['chmod', '0755', f'{exec_path}'])
        print()

        # Sign the app
        print("[*] Signing app...")
        Copy.copy_entitlements(f"{tmpfolder}/entitlements.plist", app_bundle)
        frameworks_path = os.path.join(full_app_path, 'Frameworks')
        if args.codesign:
            print("Signing with codesign as it was specified...")
            subprocess.run(
                ['security', 'import', './dev_certificate.p12', '-A'], stdout=DEVNULL)

            subprocess.run(['codesign', '-s', 'We Do A Little Trolling iPhone OS Application Signing',
                           '--force', '--deep', '--preserve-metadata=entitlements', f'{full_app_path}'], stdout=DEVNULL)

            if Path(frameworks_path).exists():
                if args.debug:
                    print("[DEBUG] Frameworks path exists")

                for file in os.listdir(frameworks_path):
                    if file.endswith(".dylib"):
                        print(f"Signing dylib {file}...")
                        subprocess.run(['codesign', '-s', 'We Do A Little Trolling iPhone OS Application Signing',
                                       '--force', '--deep', f'{frameworks_path}/{file}'], stdout=DEVNULL)

                for fpath in glob(frameworks_path + '/*.framework'):
                    fname = os.path.basename(fpath)
                    if Path(f"{fpath}/Info.plist").exists():
                        with open(f"{fpath}/Info.plist", 'rb') as f:
                            info = plistlib.load(f)
                            if info["CFBundleExecutable"]:
                                f_executable = info["CFBundleExecutable"]
                                if args.debug:
                                    print(
                                        f"[DEBUG] Executable found in the {fname}")
                            else:
                                f_executable = None
                                if args.debug:
                                    print(
                                        f"[DEBUG] No executable found in the {fname}")
                            if f_executable is not None:
                                print(f"Signing executable in {fname}")
                                f_exec_path = os.path.join(fpath, f_executable)
                                if args.debug:
                                    print(
                                        f"[DEBUG] Running command: codesign -s 'We Do A Little Trolling iPhone OS Application Signing' --force --deep {f_exec_path}")
                                subprocess.run(['codesign', '-s', 'We Do A Little Trolling iPhone OS Application Signing',
                                               '--force', '--deep', f'{f_exec_path}'], stdout=DEVNULL)
        else:
            print("Signing with ldid...")
            if ldid_in_path:
                if args.debug:
                    print(
                        f"[DEBUG] Running command: ldid -S{tmpfolder}/entitlements.plist -M -Kdev_certificate.p12 '{full_app_path}'")

                subprocess.run(['ldid', f'-S{tmpfolder}/entitlements.plist', '-M',
                               '-Kdev_certificate.p12', f'{full_app_path}'], stdout=DEVNULL)
            else:
                subprocess.run("chmod +x ldid".split(),
                               stdout=subprocess.DEVNULL)
                if args.debug:
                    print(
                        f"[DEBUG] Running command: ./ldid -S{tmpfolder}/entitlements.plist -M -Kdev_certificate.p12 '{full_app_path}'")

                subprocess.run(['./ldid', f'-S{tmpfolder}/entitlements.plist', '-M',
                               '-Kdev_certificate.p12', f'{full_app_path}'], stdout=DEVNULL)

            if Path(frameworks_path).exists():
                if args.debug:
                    print("[DEBUG] Frameworks path exists")

                for file in os.listdir(frameworks_path):
                    if file.endswith(".dylib"):
                        print(f"Signing dylib {file}...")
                        if ldid_in_path:
                            if args.debug:
                                print(
                                    f"[DEBUG] Running command: ldid -Kdev_certificate.p12 {frameworks_path}/{file}")

                            subprocess.run(
                                ['ldid', '-Kdev_certificate.p12', f'{frameworks_path}/{file}'])
                        else:
                            if args.debug:
                                print(
                                    f"[DEBUG] Running command: ./ldid -Kdev_certificate.p12 {frameworks_path}/{file}")

                            subprocess.run(
                                ['./ldid', '-Kdev_certificate.p12', f'{frameworks_path}/{file}'])

                for fpath in glob(frameworks_path + '/*.framework'):
                    fname = os.path.basename(fpath)
                    if Path(f"{fpath}/Info.plist").exists():
                        with open(f"{fpath}/Info.plist", 'rb') as f:
                            info = plistlib.load(f)
                            if info["CFBundleExecutable"]:
                                f_executable = info["CFBundleExecutable"]
                                if args.debug:
                                    print(
                                        f"[DEBUG] Executable found in the {fname}")
                            else:
                                f_executable = None
                                if args.debug:
                                    print(
                                        f"[DEBUG] No executable found in the {fname}")
                            if f_executable is not None:
                                print(f"Signing executable in {fname}")
                                f_exec_path = os.path.join(fpath, f_executable)
                                if ldid_in_path:
                                    if args.debug:
                                        print(
                                            f"[DEBUG] Running command: ldid -Kdev_certificate.p12 {f_exec_path}")
                                    subprocess.run(
                                        ['ldid', '-Kdev_certificate.p12', f'{f_exec_path}'], stdout=DEVNULL)
                                else:
                                    if args.debug:
                                        print(
                                            f"[DEBUG] Running command: ./ldid -Kdev_certificate.p12 {f_exec_path}")
                                    subprocess.run(
                                        ['./ldid', '-Kdev_certificate.p12', f'{f_exec_path}'], stdout=DEVNULL)
        print()

        # Package the deb file
        print("[*] Packaging the deb file...")
        out_deb_name = app_name.replace(' ', '')
        os.makedirs("output", exist_ok=True)
        if Path(f"output/{out_deb_name}.deb").exists():
            os.remove(f"output/{out_deb_name}.deb")

        global dpkg_cmd
        if args.output:
            dpkg_cmd = f"dpkg-deb -Zxz --root-owner-group -b {tmpfolder}/deb {args.output}"
        else:
            dpkg_cmd = f"dpkg-deb -Zxz --root-owner-group -b {tmpfolder}/deb output/{out_deb_name}.deb"

        if dpkg_in_path:
            if args.debug:
                print(f"[DEBUG] Running command: {dpkg_cmd}")

            subprocess.run(f"{dpkg_cmd}".split(), stdout=subprocess.DEVNULL)
        else:
            if args.debug:
                print(f"[DEBUG] Running command: ./{dpkg_cmd}")

            subprocess.run(f"./{dpkg_cmd}".split(), stdout=subprocess.DEVNULL)

        is_installed = False
        if not args.noinstall:
            option = 'n'
            if not args.install:
                option = input(
                    "[?] Would you like install the application to your device (must be connected)? [y, n]: ").lower()

            if option == 'y' or args.install:
                if is_macos() or is_linux():
                    try:
                        mux = USBMux()
                        if not mux.devices:
                            mux.process(1.0)
                        if not mux.devices:
                            print("Did not find a connected device")
                        else:
                            print("Found a connected device")
                            Installer.install_deb(args, out_deb_name)
                            is_installed = True
                    except ConnectionRefusedError:
                        print("Did not find a connected device")
                        pass
                elif is_ios():
                    print("Checking if user is in sudoers")
                    p = subprocess.run('sudo -nv'.split(),
                                       stdout=PIPE, stderr=PIPE)
                    if p.returncode == 0 or 'password' in p.stderr.decode():
                        print("User is in sudoers, using sudo command")
                        if args.output:
                            subprocess.run(
                                f"sudo dpkg -i {args.output}".split(), stdout=PIPE, stderr=PIPE)
                        else:
                            subprocess.run(
                                f"sudo dpkg -i output/{out_deb_name}.deb".split(), stdout=PIPE, stderr=PIPE)

                        subprocess.run(
                            f"sudo apt-get install -f".split(), stdout=PIPE, stderr=PIPE)
                    else:
                        print("User is not in sudoers, using su instead")
                        if args.output:
                            subprocess.run(
                                f"su root -c 'dpkg -i {args.output}'".split(), stdout=PIPE, stderr=PIPE)
                        else:
                            subprocess.run(
                                f"su root -c 'dpkg -i output/{out_deb_name}.deb'".split(), stdout=PIPE, stderr=PIPE)

                        subprocess.run(
                            f"su root -c 'apt-get install -f'".split(), stdout=PIPE, stderr=PIPE)

    # Done!!!
    print()
    print("[*] We are finished!")

    if is_installed:
        print(
            "[*] The application was installed to your device, no further steps are required!")
    else:
        print("[*] Copy the newly created deb from the output folder to your jailbroken iDevice and install it!")

    print("[*] The app will continue to work when rebooted to stock.")

    if args.output:
        print(f"[*] Output file: {args.output}")
    else:
        print(f"[*] Output file: output/{out_deb_name}.deb")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--codesign', action='store_true',
                        help="uses codesign instead of ldid")
    parser.add_argument('-d', '--debug', action='store_true',
                        help="shows some debug info, only useful for testing")
    parser.add_argument('-u', '--url', type=str,
                        help="the direct URL of the IPA to be signed")
    parser.add_argument('-p', '--path', type=str,
                        help="the direct local path of the IPA to be signed")
    parser.add_argument('-i', '--install', action='store_true',
                        help="installs the application to your device")
    parser.add_argument('-n', '--noinstall',
                        action='store_true', help="skips the install prompt")
    parser.add_argument('-o', '--output', type=str,
                        help="specify output file")
    args = parser.parse_args()

    main(args)
