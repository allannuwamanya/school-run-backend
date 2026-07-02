from rest_framework import renderers
import json


class Renderer(renderers.JSONRenderer):
    charset = 'utf-8'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        status_code = renderer_context['response'].status_code
        response_data = {
            'success': True if status_code < 400 else False,
            'status_code': status_code,
            'data': data,
            'message': ''
        }

        if 'ErrorDetail' in str(data) or status_code >= 400:
            response_data['errors'] = data
            response_data['data'] = None
            if isinstance(data, dict) and 'detail' in data:
                response_data['message'] = data['detail']

        return json.dumps(response_data)
