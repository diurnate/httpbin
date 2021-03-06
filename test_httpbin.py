#!/usr/bin/env python
# -*- coding: utf-8 -*-
import base64
import unittest
import six
import json
from werkzeug.http import parse_dict_header
from hashlib import md5
from six import BytesIO

import httpbin


def _string_to_base64(string):
    """Encodes string to utf-8 and then base64"""
    utf8_encoded = string.encode('utf-8')
    return base64.urlsafe_b64encode(utf8_encoded)


class HttpbinTestCase(unittest.TestCase):
    """Httpbin tests"""

    def setUp(self):
        httpbin.app.debug = True
        self.app = httpbin.app.test_client()

    def test_base64(self):
        greeting = u'Здравствуй, мир!'
        b64_encoded = _string_to_base64(greeting)
        response = self.app.get(b'/base64/' + b64_encoded)
        content = response.data.decode('utf-8')
        self.assertEqual(greeting, content)

    def test_post_binary(self):
        response = self.app.post('/post',
                                 data=b'\x01\x02\x03\x81\x82\x83',
                                 content_type='application/octet-stream')
        self.assertEqual(response.status_code, 200)

    def test_post_body_text(self):
        with open('httpbin/core.py') as f:
            response = self.app.post('/post', data={"file": f.read()})
        self.assertEqual(response.status_code, 200)

    def test_post_body_binary(self):
        with open('httpbin/core.pyc', 'rb') as f:
            response = self.app.post('/post', data={"file": f.read()})
        self.assertEqual(response.status_code, 200)

    def test_post_body_unicode(self):
        response = self.app.post('/post', data=u'оживлённым'.encode('utf-8'))
        self.assertEqual(json.loads(response.data.decode('utf-8'))['data'], u'оживлённым')

    def test_post_file_with_missing_content_type_header(self):
        # I built up the form data manually here because I couldn't find a way
        # to convince the werkzeug test client to send files without the
        # content-type of the file set.
        data = '--bound\r\nContent-Disposition: form-data; name="media"; '
        data += 'filename="test.bin"\r\n\r\n\xa5\xc6\n--bound--\r\n'
        response = self.app.post(
            '/post',
            content_type='multipart/form-data; boundary=bound',
            data=data,
        )
        self.assertEqual(response.status_code, 200)

    def test_set_cors_headers_after_request(self):
        response = self.app.get('/get')
        self.assertEqual(
            response.headers.get('Access-Control-Allow-Origin'), '*'
        )

    def test_set_cors_credentials_headers_after_auth_request(self):
        response = self.app.get('/basic-auth/foo/bar')
        self.assertEqual(
            response.headers.get('Access-Control-Allow-Credentials'), 'true'
        )

    def test_set_cors_headers_after_request_with_request_origin(self):
        response = self.app.get('/get', headers={'Origin': 'origin'})
        self.assertEqual(
            response.headers.get('Access-Control-Allow-Origin'), 'origin'
        )

    def test_set_cors_headers_with_options_verb(self):
        response = self.app.open('/get', method='OPTIONS')
        self.assertEqual(
            response.headers.get('Access-Control-Allow-Origin'), '*'
        )
        self.assertEqual(
            response.headers.get('Access-Control-Allow-Credentials'), 'true'
        )
        self.assertEqual(
            response.headers.get('Access-Control-Allow-Methods'),
            'GET, POST, PUT, DELETE, PATCH, OPTIONS'
        )
        self.assertEqual(
            response.headers.get('Access-Control-Max-Age'), '3600'
        )
        # FIXME should we add any extra headers?
        self.assertNotIn(
            'Access-Control-Allow-Headers', response.headers
        )

    def test_user_agent(self):
        response = self.app.get(
            '/user-agent', headers={'User-Agent': 'test'}
        )
        self.assertIn('test', response.data.decode('utf-8'))
        self.assertEqual(response.status_code, 200)

    def test_gzip(self):
        response = self.app.get('/gzip')
        self.assertEqual(response.status_code, 200)

    def test_digest_auth_with_wrong_password(self):
        auth_header = 'Digest username="user",realm="wrong",nonce="wrong",uri="/digest-auth/user/passwd",response="wrong",opaque="wrong"'
        response = self.app.get(
            '/digest-auth/auth/user/passwd',
            environ_base={
                # httpbin's digest auth implementation uses the remote addr to
                # build the nonce
                'REMOTE_ADDR': '127.0.0.1',
            },
            headers={
                'Authorization': auth_header,
            }
        )
        assert 'Digest' in response.headers.get('WWW-Authenticate')

    def test_digest_auth(self):
        # make first request
        unauthorized_response = self.app.get(
            '/digest-auth/auth/user/passwd',
            environ_base={
                # digest auth uses the remote addr to build the nonce
                'REMOTE_ADDR': '127.0.0.1',
            }
        )
        # make sure it returns a 401
        self.assertEqual(unauthorized_response.status_code, 401)
        header = unauthorized_response.headers.get('WWW-Authenticate')
        auth_type, auth_info = header.split(None, 1)

        # Begin crappy digest-auth implementation
        d = parse_dict_header(auth_info)
        a1 = b'user:' + d['realm'].encode('utf-8') + b':passwd'
        ha1 = md5(a1).hexdigest().encode('utf-8')
        a2 = b'GET:/digest-auth/auth/user/passwd'
        ha2 = md5(a2).hexdigest().encode('utf-8')
        a3 = ha1 + b':' + d['nonce'].encode('utf-8') + b':' + ha2
        auth_response = md5(a3).hexdigest()
        auth_header = 'Digest username="user",realm="' + \
            d['realm'] + \
            '",nonce="' + \
            d['nonce'] + \
            '",uri="/digest-auth/auth/user/passwd",response="' + \
            auth_response + \
            '",opaque="' + \
            d['opaque'] + '"'

        # make second request
        authorized_response = self.app.get(
            '/digest-auth/auth/user/passwd',
            environ_base={
                # httpbin's digest auth implementation uses the remote addr to
                # build the nonce
                'REMOTE_ADDR': '127.0.0.1',
            },
            headers={
                'Authorization': auth_header,
            }
        )

        # done!
        self.assertEqual(authorized_response.status_code, 200)

    def test_drip(self):
        response = self.app.get('/drip?numbytes=400&duration=2&delay=1')
        self.assertEqual(len(response.get_data()), 400)
        self.assertEqual(response.status_code, 200)

    def test_drip_with_custom_code(self):
        response = self.app.get('/drip?numbytes=400&duration=2&code=500')
        self.assertEqual(len(response.get_data()), 400)
        self.assertEqual(response.status_code, 500)

    def test_get_bytes(self):
        response = self.app.get('/bytes/1024')
        self.assertEqual(len(response.get_data()), 1024)
        self.assertEqual(response.status_code, 200)

    def test_bytes_with_seed(self):
        response = self.app.get('/bytes/10?seed=0')
        # The RNG changed in python3, so even though we are
        # setting the seed, we can't expect the value to be the
        # same across both interpreters.
        if six.PY3:
            self.assertEqual(
                response.data, b'\xc5\xd7\x14\x84\xf8\xcf\x9b\xf4\xb7o'
            )
        else:
            self.assertEqual(
                response.data, b'\xd8\xc2kB\x82g\xc8Mz\x95'
            )

    def test_stream_bytes(self):
        response = self.app.get('/stream-bytes/1024')
        self.assertEqual(len(response.get_data()), 1024)
        self.assertEqual(response.status_code, 200)

    def test_stream_bytes_with_seed(self):
        response = self.app.get('/stream-bytes/10?seed=0')
        # The RNG changed in python3, so even though we are
        # setting the seed, we can't expect the value to be the
        # same across both interpreters.
        if six.PY3:
            self.assertEqual(
                response.data, b'\xc5\xd7\x14\x84\xf8\xcf\x9b\xf4\xb7o'
            )
        else:
            self.assertEqual(
                response.data, b'\xd8\xc2kB\x82g\xc8Mz\x95'
            )

    def test_delete_endpoint_returns_body(self):
        response = self.app.delete(
            '/delete',
            data={'name': 'kevin'},
            content_type='application/x-www-form-urlencoded'
        )
        form_data = json.loads(response.data.decode('utf-8'))['form']
        self.assertEqual(form_data, {'name': 'kevin'})

    def test_methods__to_status_endpoint(self):
        methods = [
            'GET',
            'HEAD',
            'POST',
            'PUT',
            'DELETE',
            'PATCH',
            'TRACE',
        ]
        for m in methods:
            response = self.app.open(path='/status/418', method=m)
            self.assertEqual(response.status_code, 418)

    def test_xml_endpoint(self):
        response = self.app.get(path='/xml')
        self.assertEqual(
            response.headers.get('Content-Type'), 'application/xml'
        )

    def test_x_forwarded_proto(self):
        response = self.app.get(path='/get', headers={
            'X-Forwarded-Proto':'https'
        })
        assert json.loads(response.data.decode('utf-8'))['url'].startswith('https://')


if __name__ == '__main__':
    unittest.main()
