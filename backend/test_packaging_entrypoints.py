import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PackagingEntrypointTestCase(unittest.TestCase):
    def test_windows_and_macos_package_the_shared_backend_entrypoint(self):
        windows_script = (ROOT / "scripts" / "build-backend-sidecar.ps1").read_text(
            encoding="utf-8"
        )
        macos_spec = (
            ROOT / "backend" / "mutinychat-backend-aarch64-apple-darwin.spec"
        ).read_text(encoding="utf-8")

        self.assertIn('Join-Path $BackendDir "main.py"', windows_script)
        self.assertIn("['main.py']", macos_spec)
        self.assertNotIn("sidecar.py", windows_script)
        self.assertNotIn("sidecar.py", macos_spec)
        self.assertFalse((ROOT / "backend" / "sidecar.py").exists())

    def test_unused_opener_plugin_and_cryptography_dependency_are_absent(self):
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        capability = json.loads(
            (ROOT / "src-tauri" / "capabilities" / "default.json").read_text(
                encoding="utf-8"
            )
        )
        cargo_manifest = (ROOT / "src-tauri" / "Cargo.toml").read_text(
            encoding="utf-8"
        )
        rust_host = (ROOT / "src-tauri" / "src" / "lib.rs").read_text(
            encoding="utf-8"
        )
        runtime_requirements = (ROOT / "backend" / "requirements.txt").read_text(
            encoding="utf-8"
        )
        windows_requirements = (
            ROOT / "backend" / "requirements-windows.lock"
        ).read_text(encoding="utf-8")
        windows_build = (
            ROOT / "scripts" / "build-backend-sidecar.ps1"
        ).read_text(encoding="utf-8")
        macos_spec = (
            ROOT / "backend" / "mutinychat-backend-aarch64-apple-darwin.spec"
        ).read_text(encoding="utf-8")

        self.assertNotIn("@tauri-apps/plugin-opener", package["dependencies"])
        self.assertNotIn("opener:default", capability["permissions"])
        self.assertNotIn("tauri-plugin-opener", cargo_manifest)
        self.assertNotIn("tauri_plugin_opener", rust_host)
        self.assertNotIn("cryptography", runtime_requirements.lower())
        self.assertNotIn("cryptography", windows_requirements.lower())
        self.assertIn('"--exclude-module", "cryptography"', windows_build)
        self.assertNotIn('"--collect-all", "stem"', windows_build)
        self.assertIn('"--hidden-import", "_cffi_backend"', windows_build)
        self.assertIn("excludes=['cryptography']", macos_spec)
        self.assertIn("hiddenimports=['_cffi_backend']", macos_spec)

    def test_desktop_host_uses_fixed_debug_backend_and_enforces_bundled_tor(self):
        rust_host = (ROOT / "src-tauri" / "src" / "lib.rs").read_text(
            encoding="utf-8"
        )

        self.assertIn('env!("CARGO_MANIFEST_DIR")', rust_host)
        self.assertNotIn("backend_search_roots", rust_host)
        self.assertNotIn("backend_exec_candidates", rust_host)
        self.assertNotIn("backend_script_candidates", rust_host)
        self.assertNotIn("std::env::current_dir()", rust_host)
        self.assertNotIn("std::env::current_exe()", rust_host)
        self.assertIn(
            'command.env("MUTINYCHAT_REQUIRE_BUNDLED_TOR", "1")', rust_host
        )

    def test_username_is_session_only_and_legacy_storage_is_removed(self):
        app_source = (ROOT / "src" / "App.svelte").read_text(encoding="utf-8")
        privacy_helper = (ROOT / "src" / "lib" / "usernamePrivacy.js").read_text(
            encoding="utf-8"
        )

        self.assertNotRegex(
            app_source,
            r"localStorage\.(?:getItem|setItem)\([^)]*USERNAME",
        )
        self.assertIn("clearLegacyUsernamePreference(window.localStorage)", app_source)
        self.assertIn('"mutinychat-username"', privacy_helper)


if __name__ == "__main__":
    unittest.main()
