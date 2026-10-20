class AdminPrivacyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/manage/"):
            response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
            response["Cache-Control"] = "no-store, private"
        return response
