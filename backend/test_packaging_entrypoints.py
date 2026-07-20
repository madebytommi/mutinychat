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


if __name__ == "__main__":
    unittest.main()
