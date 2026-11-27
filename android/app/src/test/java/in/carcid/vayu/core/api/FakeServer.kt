package `in`.carcid.vayu.core.api

import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest

/** A fake Vayu API that answers by route ("POST auth/login"), so tests don't depend on request order. */
class FakeServer {
    private val routes = mutableMapOf<String, MockResponse>()
    /** Answers that also depend on the query ("page=2"): checked before [routes]. */
    private val byQuery = mutableListOf<Triple<String, String, MockResponse>>()
    /** Every request received: route and body. */
    val requests = java.util.concurrent.CopyOnWriteArrayList<Pair<String, String>>()
    /** Every query string received ("date_from=…&stage=…"), to check filters. */
    val queries = java.util.concurrent.CopyOnWriteArrayList<String>()
    private val server = MockWebServer().apply {
        dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                val path = request.requestUrl!!.encodedPath.removePrefix("/api/v1/")
                requests.add("${request.method} $path" to request.body.readUtf8())
                request.requestUrl!!.encodedQuery?.let { queries.add(java.net.URLDecoder.decode(it, "UTF-8")) }
                val query = request.requestUrl!!.encodedQuery.orEmpty()
                return synchronized(routes) {
                    byQuery.lastOrNull { it.first == "${request.method} $path" && it.second in query }?.third
                        ?: routes["${request.method} $path"] }
                    ?: MockResponse().setResponseCode(404).setBody("""{"code":"NOT_FOUND","detail":"no route"}""")
            }
        }
        start()
    }
    val url: String get() = server.url("/api/v1/").toString()

    /** Answer [route] with [body] from now on (replaces any earlier answer); [lateMs]: answer that much later. */
    fun on(route: String, body: String, code: Int = 200, headers: Map<String, String> = emptyMap(), lateMs: Long = 0) = synchronized(routes) {
        routes[route] = MockResponse().setResponseCode(code).setBody(body).apply { headers.forEach { (k, v) -> setHeader(k, v) } }
            .setHeadersDelay(lateMs, java.util.concurrent.TimeUnit.MILLISECONDS)
    }

    /** Answer [route] with [body] when its query contains [part] (e.g. "page=2"). */
    fun onQuery(route: String, part: String, body: String) = synchronized(routes) {
        byQuery += Triple(route, part, MockResponse().setResponseCode(200).setBody(body))
    }

    /** A full URL on this server outside the API (signed storage URLs). */
    fun raw(path: String): String = server.url(path).toString()

    fun bodiesOf(route: String): List<String> = requests.filter { it.first == route }.map { it.second }

    fun stop() = server.shutdown()
}

/** The app's shared parts against [server], files in a fresh folder; the outbox is run by hand. */
fun testGraph(server: FakeServer, tokens: `in`.carcid.vayu.core.auth.TokenStore = `in`.carcid.vayu.core.auth.MemoryTokenStore(),
              root: java.io.File = java.nio.file.Files.createTempDirectory("vayu").toFile()) =
    `in`.carcid.vayu.Graph(Api(server.url, tokens), tokens, root, {})
