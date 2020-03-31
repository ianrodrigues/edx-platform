# Lots of patching to stub in our own settings, and HTTP posting
import ddt
from django.conf import settings
from mock import patch
from testfixtures import LogCapture

from common.test.utils import MockS3BotoMixin
from verify_student.tests.test_models import (
    FAKE_SETTINGS,
    TestVerification,
    mock_software_secure_post,
    mock_software_secure_post_error,
    mock_software_secure_post_unavailable
)
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase

LOGGER_NAME = 'lms.djangoapps.verify_student.tasks'


@patch.dict(settings.VERIFY_STUDENT, FAKE_SETTINGS)
@patch('lms.djangoapps.verify_student.models.requests.post', new=mock_software_secure_post)
@ddt.ddt
class TestPhotoVerification(TestVerification, MockS3BotoMixin, ModuleStoreTestCase):
    def test_submissions(self):
        """Test that we set our status correctly after a submission."""
        # Basic case, things go well.
        attempt = self.create_and_submit()
        self.assertEqual(attempt.status, "submitted")
        retry_max_attempts = settings.SOFTWARE_SECURE_RETRY_MAX_ATTEMPTS

        # We post, but Software Secure doesn't like what we send for some reason
        with patch('lms.djangoapps.verify_student.tasks.requests.post', new=mock_software_secure_post_error):
            attempt = self.create_and_submit()
            self.assertEqual(attempt.status, "must_retry")

        # We try to post, but run into an error (in this case a network connection error)
        with patch('lms.djangoapps.verify_student.tasks.requests.post', new=mock_software_secure_post_unavailable):
            with LogCapture('lms.djangoapps.verify_student.tasks') as logger:
                attempt = self.create_and_submit()
                username = attempt.user.username
                self.assertEqual(attempt.status, "must_retry")
                expected_retry_log = tuple(
                    (
                        LOGGER_NAME,
                        'ERROR',
                        (
                            'Retrying sending request to Software Secure for user: %r, Receipt ID: %r '
                            'attempt#: %s of %s'
                        ) %
                        (
                            username,
                            attempt.receipt_id,
                            current_attempt,
                            settings.SOFTWARE_SECURE_RETRY_MAX_ATTEMPTS,
                        )
                    )
                    for current_attempt in range(retry_max_attempts + 1)
                )

                expected_retry_log += (
                    (
                        LOGGER_NAME,
                        'ERROR',
                        ('Software Secure submission failed for user %r, setting status to must_retry' % username)
                    ),
                )
                logger.check(*expected_retry_log)
