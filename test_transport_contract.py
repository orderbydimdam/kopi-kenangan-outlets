import json
import unittest
from unittest import mock

from api import menu, transport


class FakeResponse:
    def __init__(self, body=b'{}', status=200, content_type='application/json', content_length=None):
        self.body = body
        self.status = status
        self.headers = {'Content-Type': content_type}
        if content_length is not None:
            self.headers['Content-Length'] = str(content_length)

    def read(self, size=-1):
        return self.body if size == -1 else self.body[:size]

    def close(self):
        pass


class TransportContractTests(unittest.TestCase):
    def request(self, response):
        with mock.patch.object(transport, '_open', return_value=response):
            return transport.request_json('/test', b'{}', {})

    def test_rejects_redirect_status_wrong_mime_and_bad_lengths(self):
        body = b'{}'
        cases = [
            FakeResponse(body=body, status=302, content_length=len(body)),
            FakeResponse(body=body, content_type='text/html', content_length=len(body)),
            FakeResponse(body=body, content_length='bad'),
            FakeResponse(body=body, content_length=len(body) + 1),
            FakeResponse(body=b'x' * (transport.MAX_BODY_BYTES + 1), content_length=transport.MAX_BODY_BYTES + 1),
        ]
        for response in cases:
            with self.subTest(response=response):
                with self.assertRaises(transport.IntegrationError):
                    self.request(response)

    def test_accepts_json_charset_content_type(self):
        body = b'{"ok":true}'

        self.assertEqual(self.request(FakeResponse(body=body, content_type='application/json; charset=utf-8', content_length=len(body))), {'ok': True})

    def test_accepts_missing_content_length_when_body_is_bounded(self):
        body = b'{"ok":true}'

        self.assertEqual(self.request(FakeResponse(body=body)), {'ok': True})

    def test_fixed_json_transport_uses_timeout_and_no_redirect_opener(self):
        body = b'{"ok":true}'
        response = FakeResponse(body=body, content_length=len(body))
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch.object(transport.urllib.request, 'build_opener', return_value=opener) as build:
            self.assertEqual(transport.request_json('/test', body, {}), {'ok': True})
        build.assert_called_once()
        opener.open.assert_called_once()
        self.assertEqual(opener.open.call_args.kwargs['timeout'], transport.REQUEST_TIMEOUT)

    def test_menu_wrapper_is_testable_at_api_boundary(self):
        with mock.patch.object(menu, 'request_json', return_value={'ok': True}) as request:
            self.assertEqual(menu._request_json('/test', b'{}', {}), {'ok': True})
        request.assert_called_once_with('/test', b'{}', {})

    def test_token_response_requires_canonical_nonempty_token(self):
        for value in ('', ' synthetic-token ', None, 1):
            with self.subTest(value=value):
                payload = {'data': {'web_order_session_token': value}}
                with mock.patch.object(menu, '_request_json', return_value=payload):
                    menu._token.update(val=None, t=0)
                    with self.assertRaises(menu.IntegrationError):
                        menu.get_token()

    def test_token_response_ignores_extra_keys_but_requires_token(self):
        valid = {"error_code": 0, "data": {"customer_name": "", "web_order_session_token": "synthetic-token"}, "msg": ""}
        ok_cases = [
            {**valid, "extra": False},
            {"error_code": 0, "data": {"web_order_session_token": "synthetic-token"}, "msg": ""},
            {"error_code": 0, "data": {"customer_name": "", "web_order_session_token": "synthetic-token", "extra": False}, "msg": ""},
        ]
        for payload in ok_cases:
            with self.subTest(ok=tuple(payload)):
                with mock.patch.object(menu, "_request_json", return_value=payload):
                    menu._token.update(val=None, t=0)
                    self.assertEqual(menu.get_token(), "synthetic-token")
        bad_cases = [
            {"error_code": 0, "data": {"customer_name": ""}, "msg": ""},
            {"error_code": 0, "data": {"web_order_session_token": ""}, "msg": ""},
            {"error_code": 5, "data": {"web_order_session_token": "x"}, "msg": ""},
            [],
        ]
        for payload in bad_cases:
            with self.subTest(bad=repr(payload)[:40]):
                with mock.patch.object(menu, "_request_json", return_value=payload):
                    menu._token.update(val=None, t=0)
                    with self.assertRaises(menu.IntegrationError):
                        menu.get_token()

    def test_token_response_requires_exact_integer_zero_error_code(self):
        payload = {"error_code": False, "data": {"customer_name": "", "web_order_session_token": "synthetic-token"}, "msg": ""}
        with mock.patch.object(menu, "_request_json", return_value=payload):
            menu._token.update(val=None, t=0)
            with self.assertRaises(menu.IntegrationError):
                menu.get_token()


if __name__ == '__main__':
    unittest.main()
