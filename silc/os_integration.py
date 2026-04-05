"""Install and remove OS integration hooks for SILC."""

from __future__ import annotations

import plistlib
import shlex
import shutil
import sys
import textwrap
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path


class OsIntegrationError(RuntimeError):
    """Raised when OS integration cannot be installed or removed."""


HELPER_SCRIPT_NAME = "silc-start-here.py"
MACOS_WORKFLOW_NAME = "SILC Start.workflow"
MACOS_WORKFLOW_ENTER_NAME = "SILC Start and Enter.workflow"
NAUTILUS_SCRIPT_NAME = "SILC Start Here"
DOLPHIN_ENTER_SERVICE_NAME = "silc-start-enter-here.desktop"
DOLPHIN_SERVICE_NAME = "silc-start-here.desktop"
THUNAR_ACTION_NAME = "SILC Start Here"
THUNAR_ENTER_ACTION_NAME = "SILC Start and Enter Here"
THUNAR_ACTION_ICON = "utilities-terminal"
DEFAULT_MENU_NAME = "SILC Start Here"
DEFAULT_ENTER_MENU_NAME = "SILC Start and Enter Here"
WINDOWS_MENU_NAME = "Open SILC Here"
WINDOWS_ENTER_MENU_NAME = "Open SILC and Enter Here"
WINDOWS_REGISTRY_SUBKEY = "SilcStartHere"
WINDOWS_ENTER_REGISTRY_SUBKEY = "SilcStartEnterHere"


def install_os_integration() -> list[str]:
    """Install the current platform's file-manager integration."""

    _ensure_supported_platform()

    helper_script = _write_helper_script()
    created: list[str] = [str(helper_script)]

    if sys.platform == "darwin":
        created.extend(_install_macos_quick_action(helper_script, enter=False))
        created.extend(_install_macos_quick_action(helper_script, enter=True))
    elif sys.platform == "win32":
        created.extend(_install_windows_integrations(helper_script))
    else:
        created.extend(_install_linux_integrations(helper_script))

    return created


def uninstall_os_integration() -> list[str]:
    """Remove the current platform's file-manager integration."""

    _ensure_supported_platform()

    removed: list[str] = []

    helper_script = _helper_script_path()
    if helper_script.exists():
        helper_script.unlink()
        removed.append(str(helper_script))

    if sys.platform == "darwin":
        for workflow_dir in (_workflow_dir(False), _workflow_dir(True)):
            if workflow_dir.exists():
                shutil.rmtree(workflow_dir)
                removed.append(str(workflow_dir))
    elif sys.platform == "win32":
        removed.extend(_uninstall_windows_integrations())
    else:
        for nautilus_script in (
            _nautilus_script_path(False),
            _nautilus_script_path(True),
        ):
            if nautilus_script.exists():
                nautilus_script.unlink()
                removed.append(str(nautilus_script))

        for dolphin_service in (
            _dolphin_service_path(False),
            _dolphin_service_path(True),
        ):
            if dolphin_service.exists():
                dolphin_service.unlink()
                removed.append(str(dolphin_service))

        thunar_actions = _thunar_actions_path()
        if thunar_actions.exists() and _remove_thunar_action(thunar_actions):
            removed.append(str(thunar_actions))

    _prune_empty_directories(_integration_root())

    return removed


def _ensure_supported_platform() -> None:
    if (
        sys.platform != "darwin"
        and sys.platform != "win32"
        and not sys.platform.startswith("linux")
    ):
        raise OsIntegrationError(
            "OS integration is only supported on macOS, Windows, and Linux."
        )


def _write_helper_script() -> Path:
    integration_root = _integration_root()
    integration_root.mkdir(parents=True, exist_ok=True)
    helper_script = _helper_script_path()
    helper_script.write_text(_build_helper_script(), encoding="utf-8")
    helper_script.chmod(0o755)
    return helper_script


def _helper_script_path() -> Path:
    return _integration_root() / HELPER_SCRIPT_NAME


def _integration_root() -> Path:
    return Path.home() / ".silc" / "os-integration"


def _build_helper_script() -> str:
    return textwrap.dedent(
        """\
        #!/usr/bin/env python3
        # SILC context-menu launcher.

        from __future__ import annotations

        import os
        import sys
        from pathlib import Path
        from urllib.parse import unquote, urlparse


        def _pick_mode_and_target(argv: list[str]) -> tuple[bool, str]:
            enter = False
            args = list(argv)

            if args and args[0] == "--enter":
                enter = True
                args = args[1:]

            if args:
                return enter, args[0]
            nautilus_uri = os.environ.get("NAUTILUS_SCRIPT_CURRENT_URI")
            if nautilus_uri:
                return enter, nautilus_uri
            return enter, os.getcwd()


        def _normalize_target(raw: str) -> str:
            if raw.startswith("file://"):
                raw = unquote(urlparse(raw).path)
            path = Path(raw).expanduser()
            if path.exists() and path.is_file():
                path = path.parent
            return str(path.resolve())


        def main() -> None:
            enter, target = _pick_mode_and_target(sys.argv[1:])
            target = _normalize_target(target)
            command = "start-enter" if enter else "start"
            os.execv(
                sys.executable,
                [sys.executable, "-m", "silc", command, "--cwd", target],
            )


        if __name__ == "__main__":
            main()
        """
    )


def _python_exec() -> str:
    python = Path(sys.executable).resolve()
    if sys.platform == "win32":
        pythonw = python.with_name("pythonw.exe")
        if pythonw.exists():
            return str(pythonw)
    return str(python)


def _build_launcher_script(helper_script: Path, *, enter: bool) -> str:
    mode_arg = " --enter" if enter else ""
    return textwrap.dedent(
        f"""\
        #!/bin/sh
        exec {shlex.quote(_python_exec())} {shlex.quote(str(helper_script))}{mode_arg} "$@"
        """
    )


def _install_macos_quick_action(helper_script: Path, *, enter: bool) -> list[str]:
    workflow_dir = _workflow_dir(enter)
    contents_dir = workflow_dir / "Contents"
    contents_dir.mkdir(parents=True, exist_ok=True)

    info_plist = contents_dir / "Info.plist"
    document_wflow = contents_dir / "document.wflow"

    info_plist.write_bytes(plistlib.dumps(_workflow_info_plist(enter)))
    document_wflow.write_bytes(
        plistlib.dumps(
            _workflow_document(helper_script, python_exec=_python_exec(), enter=enter)
        )
    )

    return [str(workflow_dir), str(info_plist), str(document_wflow)]


def _workflow_dir(enter: bool) -> Path:
    workflow_name = MACOS_WORKFLOW_ENTER_NAME if enter else MACOS_WORKFLOW_NAME
    return Path.home() / "Library" / "Services" / workflow_name


def _workflow_info_plist(enter: bool) -> dict[str, object]:
    menu_name = DEFAULT_ENTER_MENU_NAME if enter else DEFAULT_MENU_NAME
    return {
        "NSServices": [
            {
                "NSBackgroundColorName": "background",
                "NSIconName": "NSActionTemplate",
                "NSMenuItem": {"default": menu_name},
                "NSMessage": "runWorkflowAsService",
                "NSRequiredContext": {"NSApplicationIdentifier": "com.apple.finder"},
                "NSSendFileTypes": ["public.item"],
            }
        ]
    }


def _workflow_document(
    helper_script: Path, python_exec: str, *, enter: bool
) -> dict[str, object]:
    mode_arg = " --enter" if enter else ""
    command = textwrap.dedent(
        f"""\
        #!/bin/sh
        set -eu
        exec {shlex.quote(python_exec)} {shlex.quote(str(helper_script))}{mode_arg} "$@"
        """
    )
    action_uuid = str(uuid.uuid4()).upper()
    input_uuid = str(uuid.uuid4()).upper()
    output_uuid = str(uuid.uuid4()).upper()

    return {
        "AMApplicationBuild": "512",
        "AMApplicationVersion": "2.10",
        "AMDocumentVersion": "2",
        "actions": [
            {
                "action": {
                    "AMAccepts": {
                        "Container": "List",
                        "Optional": True,
                        "Types": ["com.apple.cocoa.string"],
                    },
                    "AMActionVersion": "2.0.3",
                    "AMApplication": ["Automator"],
                    "AMParameterProperties": {
                        "COMMAND_STRING": {},
                        "CheckedForUserDefaultShell": {},
                        "inputMethod": {},
                        "shell": {},
                        "source": {},
                    },
                    "AMProvides": {
                        "Container": "List",
                        "Types": ["com.apple.cocoa.string"],
                    },
                    "ActionBundlePath": "/System/Library/Automator/Run Shell Script.action",
                    "ActionName": "Run Shell Script",
                    "ActionParameters": {
                        "COMMAND_STRING": command,
                        "CheckedForUserDefaultShell": True,
                        "inputMethod": 0,
                        "shell": "/bin/sh",
                        "source": "",
                    },
                    "BundleIdentifier": "com.apple.RunShellScript",
                    "CFBundleVersion": "2.0.3",
                    "CanShowSelectedItemsWhenRun": False,
                    "CanShowWhenRun": True,
                    "Category": ["AMCategoryUtilities"],
                    "Class Name": "RunShellScriptAction",
                    "InputUUID": input_uuid,
                    "Keywords": ["Shell", "Script", "Command", "Run", "Unix"],
                    "OutputUUID": output_uuid,
                    "UUID": action_uuid,
                    "UnlocalizedApplications": ["Automator"],
                    "arguments": {
                        "0": {
                            "default value": 0,
                            "name": "inputMethod",
                            "required": "0",
                            "type": "0",
                            "uuid": "0",
                        },
                        "1": {
                            "default value": False,
                            "name": "CheckedForUserDefaultShell",
                            "required": "0",
                            "type": "0",
                            "uuid": "1",
                        },
                        "2": {
                            "default value": "",
                            "name": "source",
                            "required": "0",
                            "type": "0",
                            "uuid": "2",
                        },
                        "3": {
                            "default value": "",
                            "name": "COMMAND_STRING",
                            "required": "0",
                            "type": "0",
                            "uuid": "3",
                        },
                        "4": {
                            "default value": "/bin/sh",
                            "name": "shell",
                            "required": "0",
                            "type": "0",
                            "uuid": "4",
                        },
                    },
                    "isViewVisible": 1,
                    "location": "309.000000:641.000000",
                    "nibPath": "/System/Library/Automator/Run Shell Script.action/Contents/Resources/Base.lproj/main.nib",
                },
                "isViewVisible": 1,
            }
        ],
        "connectors": {},
        "workflowMetaData": {
            "applicationBundleID": "com.apple.finder",
            "applicationBundleIDsByPath": {
                "/System/Library/CoreServices/Finder.app": "com.apple.finder",
            },
            "applicationPath": "/System/Library/CoreServices/Finder.app",
            "applicationPaths": ["/System/Library/CoreServices/Finder.app"],
            "inputTypeIdentifier": "com.apple.Automator.fileSystemObject",
            "outputTypeIdentifier": "com.apple.Automator.nothing",
            "presentationMode": 15,
            "processesInput": False,
            "serviceApplicationBundleID": "com.apple.finder",
            "serviceApplicationPath": "/System/Library/CoreServices/Finder.app",
            "serviceInputTypeIdentifier": "com.apple.Automator.fileSystemObject",
            "serviceOutputTypeIdentifier": "com.apple.Automator.nothing",
            "serviceProcessesInput": False,
            "systemImageName": "NSActionTemplate",
            "useAutomaticInputType": False,
            "workflowTypeIdentifier": "com.apple.Automator.servicesMenu",
        },
    }


def _install_linux_integrations(helper_script: Path) -> list[str]:
    created = [
        _install_nautilus_script(helper_script, enter=False),
        _install_nautilus_script(helper_script, enter=True),
        _install_dolphin_service(helper_script, enter=False),
        _install_dolphin_service(helper_script, enter=True),
    ]
    created.extend(_install_thunar_action(helper_script))
    return created


def _nautilus_script_path(enter: bool) -> Path:
    script_name = DEFAULT_ENTER_MENU_NAME if enter else NAUTILUS_SCRIPT_NAME
    return Path.home() / ".local" / "share" / "nautilus" / "scripts" / script_name


def _install_nautilus_script(helper_script: Path, *, enter: bool) -> str:
    script_path = _nautilus_script_path(enter)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(
        _build_launcher_script(helper_script, enter=enter),
        encoding="utf-8",
    )
    script_path.chmod(0o755)
    return str(script_path)


def _dolphin_service_path(enter: bool) -> Path:
    service_name = DOLPHIN_ENTER_SERVICE_NAME if enter else DOLPHIN_SERVICE_NAME
    return Path.home() / ".local" / "share" / "kio" / "servicemenus" / service_name


def _install_dolphin_service(helper_script: Path, *, enter: bool) -> str:
    service_path = _dolphin_service_path(enter)
    service_path.parent.mkdir(parents=True, exist_ok=True)
    menu_name = DEFAULT_ENTER_MENU_NAME if enter else DEFAULT_MENU_NAME
    mode_arg = " --enter" if enter else ""
    service_path.write_text(
        textwrap.dedent(
            f"""\
            [Desktop Entry]
            Type=Service
            X-KDE-ServiceTypes=KonqPopupMenu/Plugin
            MimeType=inode/directory;
            Actions={"SilcStartEnterHere" if enter else "SilcStartHere"}
            Icon=utilities-terminal

            [Desktop Action {"SilcStartEnterHere" if enter else "SilcStartHere"}]
            Name={menu_name}
            Icon=utilities-terminal
            Exec={_python_exec()} {str(helper_script)}{mode_arg} %f
            """
        ).lstrip(),
        encoding="utf-8",
    )
    return str(service_path)


def _thunar_actions_path() -> Path:
    return Path.home() / ".config" / "Thunar" / "uca.xml"


def _install_thunar_action(helper_script: Path) -> list[str]:
    uca_path = _thunar_actions_path()
    uca_path.parent.mkdir(parents=True, exist_ok=True)

    if uca_path.exists():
        try:
            root = ET.parse(uca_path).getroot()
        except ET.ParseError:
            root = ET.Element("actions")
    else:
        root = ET.Element("actions")

    for enter in (False, True):
        if _thunar_action_exists(root, helper_script, enter=enter):
            continue
        action_name = THUNAR_ENTER_ACTION_NAME if enter else THUNAR_ACTION_NAME
        mode_arg = " --enter" if enter else ""
        action = ET.SubElement(root, "action")
        ET.SubElement(action, "icon").text = THUNAR_ACTION_ICON
        ET.SubElement(action, "name").text = action_name
        ET.SubElement(action, "unique-id").text = str(uuid.uuid4())
        ET.SubElement(action, "command").text = (
            f"{_python_exec()} {str(helper_script)}{mode_arg} %f"
        )
        ET.SubElement(action, "description").text = (
            "Open the selected folder in SILC"
            if not enter
            else "Open the selected folder in SILC and enter"
        )
        ET.SubElement(action, "patterns").text = "*"
        ET.SubElement(action, "directories")

    _write_xml_tree(root, uca_path)
    return [str(uca_path)]


def _thunar_action_exists(
    root: ET.Element, helper_script: Path, *, enter: bool
) -> bool:
    mode_arg = " --enter" if enter else ""
    expected_command = f"{_python_exec()} {str(helper_script)}{mode_arg} %f"
    expected_name = THUNAR_ENTER_ACTION_NAME if enter else THUNAR_ACTION_NAME
    for action in root.findall("action"):
        name = (action.findtext("name") or "").strip()
        command = (action.findtext("command") or "").strip()
        if name == expected_name or command == expected_command:
            return True
    return False


def _remove_thunar_action(uca_path: Path) -> bool:
    try:
        root = ET.parse(uca_path).getroot()
    except ET.ParseError:
        return False

    helper_commands = {
        f"{_python_exec()} {str(_helper_script_path())} %f",
        f"{_python_exec()} {str(_helper_script_path())} --enter %f",
    }
    removed = False
    for action in list(root.findall("action")):
        name = (action.findtext("name") or "").strip()
        command = (action.findtext("command") or "").strip()
        if (
            name in {THUNAR_ACTION_NAME, THUNAR_ENTER_ACTION_NAME}
            or command in helper_commands
        ):
            root.remove(action)
            removed = True

    if not removed:
        return False

    if not root.findall("action"):
        uca_path.unlink()
    else:
        _write_xml_tree(root, uca_path)

    return True


def _write_xml_tree(root: ET.Element, path: Path) -> None:
    tree = ET.ElementTree(root)
    try:
        ET.indent(tree, space="\t")
    except AttributeError:
        pass
    tree.write(path, encoding="utf-8", xml_declaration=True)


def _windows_registry_entries() -> list[tuple[str, str, str, bool]]:
    return [
        (
            r"Software\Classes\Directory\shell\SilcStartHere",
            WINDOWS_MENU_NAME,
            "%1",
            False,
        ),
        (
            r"Software\Classes\Directory\shell\SilcStartEnterHere",
            WINDOWS_ENTER_MENU_NAME,
            "%1",
            True,
        ),
        (
            r"Software\Classes\Directory\Background\shell\SilcStartHere",
            WINDOWS_MENU_NAME,
            "%V",
            False,
        ),
        (
            r"Software\Classes\Directory\Background\shell\SilcStartEnterHere",
            WINDOWS_ENTER_MENU_NAME,
            "%V",
            True,
        ),
        (r"Software\Classes\Drive\shell\SilcStartHere", WINDOWS_MENU_NAME, "%1", False),
        (
            r"Software\Classes\Drive\shell\SilcStartEnterHere",
            WINDOWS_ENTER_MENU_NAME,
            "%1",
            True,
        ),
        (r"Software\Classes\*\shell\SilcStartHere", WINDOWS_MENU_NAME, "%1", False),
        (
            r"Software\Classes\*\shell\SilcStartEnterHere",
            WINDOWS_ENTER_MENU_NAME,
            "%1",
            True,
        ),
    ]


def _install_windows_integrations(helper_script: Path) -> list[str]:
    try:
        import winreg
    except ImportError as exc:  # pragma: no cover - Windows only
        raise OsIntegrationError("Windows registry support is unavailable.") from exc

    created = [str(helper_script)]
    python_exec = _python_exec()

    for registry_path, menu_name, placeholder, enter in _windows_registry_entries():
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, registry_path) as key:
            winreg.SetValueEx(key, "MUIVerb", 0, winreg.REG_SZ, menu_name)
            winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, python_exec)
            with winreg.CreateKeyEx(key, "command") as command_key:
                mode_arg = " --enter" if enter else ""
                winreg.SetValueEx(
                    command_key,
                    None,
                    0,
                    winreg.REG_SZ,
                    f'"{python_exec}" "{str(helper_script)}"{mode_arg} {placeholder}',
                )
        created.append(rf"HKCU\{registry_path}")

    return created


def _uninstall_windows_integrations() -> list[str]:
    try:
        import winreg
    except ImportError as exc:  # pragma: no cover - Windows only
        raise OsIntegrationError("Windows registry support is unavailable.") from exc

    removed: list[str] = []
    for registry_path, _menu_name, _placeholder, _enter in _windows_registry_entries():
        if _delete_registry_tree(winreg.HKEY_CURRENT_USER, registry_path):
            removed.append(rf"HKCU\{registry_path}")
    return removed


def _delete_registry_tree(
    root: object, path: str
) -> bool:  # pragma: no cover - Windows only
    try:
        import winreg
    except ImportError:
        return False

    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
            while True:
                try:
                    child = winreg.EnumKey(key, 0)
                except OSError:
                    break
                _delete_registry_tree(key, child)
    except FileNotFoundError:
        return False

    try:
        winreg.DeleteKey(root, path)
    except FileNotFoundError:
        return False
    return True


def _prune_empty_directories(root: Path) -> None:
    current = root
    while current != current.parent:
        if current == Path.home():
            break
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


__all__ = ["OsIntegrationError", "install_os_integration", "uninstall_os_integration"]
