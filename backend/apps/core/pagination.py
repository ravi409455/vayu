"""One pagination for every paged list (F-165): {count, next, previous, results}, 50 a page by
default, `page_size` up to 200. A page past the end is a 404 (code NOT_FOUND). Lists that are
bounded by nature (forms, integrations, problems) are plain arrays."""
from rest_framework.pagination import PageNumberPagination


class Pages(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200
