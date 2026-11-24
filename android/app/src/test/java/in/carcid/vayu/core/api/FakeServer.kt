package `in`.carcid.vayu.core.api

import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest

/** A fake Vayu API that answers by route ("POST auth/login"), so tests don't depend on request order. */
class FakeServer {
    private val routes = mutableMapOf<String, MockResponse>()
    private val server = MockWebServer().apply {
        dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                val path = request.requestUrl!!.encodedPath.removePrefix("/api/v1/")
                return synchronized(routes) { routes["${request.method} $path"] }
                    ?: MockResponse().setResponseCode(404).setBody("""{"code":"NOT_FOUND","detail":"no route"}""")
            }
        }
        start()
    }
    val url: String get() = server.url("/api/v1/").toString()

    /** Answer [route] with [body] from now on (replaces any earlier answer). */
    fun on(route: String, body: String, code: Int = 200) = synchronized(routes) {
        routes[route] = MockResponse().setResponseCode(code).setBody(body)
    }

    fun stop() = server.shutdown()
}
