from django.contrib.auth.tokens import PasswordResetTokenGenerator


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    # A distinct salt from Django's own password-reset generator — otherwise
    # this would silently share PasswordResetTokenGenerator's namespace.
    key_salt = "account.EmailVerificationTokenGenerator"

    def _make_hash_value(self, user, timestamp):
        # Folding email_verified into the hash means a link stops validating
        # the moment it's used once, without a stateful token table.
        return f"{super()._make_hash_value(user, timestamp)}{user.email_verified}"


email_verification_token = EmailVerificationTokenGenerator()
