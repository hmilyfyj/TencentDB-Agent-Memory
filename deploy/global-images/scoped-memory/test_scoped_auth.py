import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import scoped_auth
from scoped_memory import Denied


class ScopedAuthTests(unittest.TestCase):
    def test_scope_denial_precedes_credential_resolution_and_suppresses_details(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = home / 'scope-config.json'
            config.write_text(json.dumps({}))
            config.chmod(0o600)
            resolver = Mock(return_value='synthetic-token')
            with patch.object(scoped_auth, '__file__', str(home / 'scoped_auth.py')), \
                    patch.object(scoped_auth, 'context', side_effect=Denied('sensitive detail')), \
                    patch.dict('sys.modules', project_auth=SimpleNamespace(resolve=resolver)):
                output, error = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
                    self.assertEqual(scoped_auth.main(), 1)
                resolver.assert_not_called()
                self.assertEqual(output.getvalue(), '')
                self.assertNotIn('sensitive detail', error.getvalue())


if __name__ == '__main__':
    unittest.main()
