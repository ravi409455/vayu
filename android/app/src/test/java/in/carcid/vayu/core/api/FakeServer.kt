package `in`.carcid.vayu.core.api

import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest

/** A fake Vayu API that answers by route ("POST auth/login"), so tests don't depend on request order. */
class FakeServer {
    private val routes = mutableMapOf<String, MockResponse>()
    /** Every request received: route and body. */
    val requests = java.util.Collections.synchronizedList(mutableListOf<Pair<String, String>>())
    private val server = MockWebServer().apply {
        dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                val path = request.requestUrl!!.encodedPath.removePrefix("/api/v1/")
                requests.add("${request.method} $path" to request.body.readUtf8())
                return synchronized(routes) { routes["${request.method} $path"] }
                    ?: MockResponse().setResponseCode(404).setBody("""{"code":"NOT_FOUND","detail":"no route"}""")
            }
        }
        start()
    }
    val url: String get() = server.url("/api/v1/").toString()

    /** Answer [route] with [body] from now on (replaces any earlier answer). */
    fun on(route: String, body: String, code: Int = 200, headers: Map<String, String> = emptyMap()) = synchronized(routes) {
        routes[route] = MockResponse().setResponseCode(code).setBody(body).apply { headers.forEach { (k, v) -> setHeader(k, v) } }
    }

    /** A full URL on this server outside the API (signed storage URLs). */
    fun raw(path: String): String = server.url(path).toString()

    fun bodiesOf(route: String): List<String> = requests.filter { it.first == route }.map { it.second }

    fun stop() = server.shutdown()
}

/** The app's shared parts against [server], files in a fresh folder; the outbox is run by hand. */
fun testGraph(server: FakeServer, tokens: `in`.carcid.vayu.core.auth.TokenStore = `in`.carcid.vayu.core.auth.MemoryTokenStore(),
              root: java.io.File = java.nio.file.Files.createTempDirectory("vayu").toFile()) =
    `in`.carcid.vayu.Graph(Api(server.url, tokens), tokens, root) {}
