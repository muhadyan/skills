import unittest

import helpers  # noqa: F401  (puts scripts/ on sys.path)

from vault_memory import scrub

M = scrub.MARKER


class ScrubTest(unittest.TestCase):
    def check(self, text, expected):
        out, hits = scrub.scrub(text)
        self.assertEqual(out, expected)
        return hits

    def test_key_value_pairs(self):
        hits = self.check("PGPASSWORD=s3cr3tPass psql -h db", f"PGPASSWORD={M} psql -h db")
        self.assertEqual(len(hits), 1)
        self.check('api_key: "AbC123xyz789"', f'api_key: "{M}"')
        self.check("DB_PASSWORD = hunter2hunter2", f"DB_PASSWORD = {M}")
        self.check("Client secret is `9f8e7d6c5b4a`", f"Client secret is `{M}`")

    def test_known_token_shapes(self):
        self.check("key sk-ant-api03-abcdefghijklmnopqrstu end", f"key {M} end")
        self.check("ghp_abcdefghijklmnopqrstuvwxyz0123456789", M)
        self.check("AKIAABCDEFGHIJKLMNOP", M)
        self.check("Authorization: Bearer abcdefghijklmnop1234", f"Authorization: Bearer {M}")
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        self.check(f"token {jwt}", f"token {M}")

    def test_real_values_next_to_words(self):
        self.check("raw_password=73c5k8xq shown in admin", f"raw_password={M} shown in admin")
        self.check('--data-urlencode "access_token=1042817736EAAB"', f'--data-urlencode "access_token={M}"')

    def test_quoted_passphrase_pem_and_long_letters(self):
        self.check('password: "my secret pass phrase"', f'password: "{M}"')
        self.check("api_key=ABCDEFGHIJKLMNOPQRST", f"api_key={M}")
        pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEabc\n-----END RSA PRIVATE KEY-----"
        self.check(f"key:\n{pem}\nend", f"key:\n{M}\nend")

    def test_literals(self):
        out, hits = scrub.scrub("Local Postgres (`postgres`/`hunter42`) and `hunter42`, again", ("hunter42",))
        self.assertEqual(out, f"Local Postgres (`postgres`/`{M}`) and `{M}`, again")
        self.assertEqual([h.kind for h in hits], ["literal", "literal"])

    def test_connection_string_password(self):
        self.check("postgres://app:Sup3rS3cret@10.0.0.5:5432/db",
                   f"postgres://app:{M}@10.0.0.5:5432/db")

    def test_near_misses_are_kept(self):
        for text in (
            "Rotate the token weekly; the password policy needs 12 chars.",
            "password: <set in .env>",
            "API_KEY=${ANTHROPIC_API_KEY}",
            "token: $GITHUB_TOKEN",
            "secret: see 1Password item 'Admos prod'",
            "postgres://localhost:5432/db",
            "Use the tokenizer from tokens.py",
            "password=xxxxxxxx",
            "the proof the secret is genuine.",
            "token = grafana.com policy",
            "Longer token = longer-lived credential",
            "token=jwt_encode(p)",
            "`const token = getJwtToken()`",
            "Laravel `ResetPasswordController::reset` sends mail",
            "forces `password=bcrypt(random)`",
            "password = **copied** from the verifier",
            "Access token is **in-memory** only",
            "refresh token is `window.location.pathname`",
        ):
            out, hits = scrub.scrub(text)
            self.assertEqual(out, text, text)
            self.assertEqual(hits, [], text)

    def test_hits_report_line_and_masked_preview(self):
        _, hits = scrub.scrub("a\nPGPASSWORD=s3cr3tPass\n")
        self.assertEqual(hits[0].line, 2)
        self.assertNotIn("s3cr3tPass", hits[0].preview)


if __name__ == "__main__":
    unittest.main()
