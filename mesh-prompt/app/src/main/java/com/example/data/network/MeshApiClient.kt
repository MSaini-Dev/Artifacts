package com.example.data.network

import com.example.data.model.MeshMessageItem
import com.example.data.model.MeshNodeInfo
import com.example.data.model.MeshStatus
import com.example.data.model.PromptResponse
import com.squareup.moshi.Moshi
import com.squareup.moshi.Types
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.ConnectException
import java.net.NoRouteToHostException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import java.util.concurrent.TimeUnit

sealed class ApiResult<out T> {
    data class Success<out T>(val data: T) : ApiResult<T>()
    data class Error(val message: String, val statusCode: Int? = null) : ApiResult<Nothing>()
}

class MeshApiClient {
    private val moshi = Moshi.Builder()
        .addLast(KotlinJsonAdapterFactory())
        .build()

    private val statusAdapter = moshi.adapter(MeshStatus::class.java)
    private val messageListAdapter = moshi.adapter<List<MeshMessageItem>>(
        Types.newParameterizedType(List::class.java, MeshMessageItem::class.java)
    )

    private val statusClient = OkHttpClient.Builder()
        .connectTimeout(6, TimeUnit.SECONDS)
        .readTimeout(8, TimeUnit.SECONDS)
        .writeTimeout(8, TimeUnit.SECONDS)
        .retryOnConnectionFailure(true)
        .build()

    private val promptClient = OkHttpClient.Builder()
        .connectTimeout(12, TimeUnit.SECONDS)
        .readTimeout(300, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .retryOnConnectionFailure(false)
        .build()

    private val jsonMediaType = "application/json; charset=utf-8".toMediaType()

    fun normalizeUrl(rawUrl: String): String {
        var trimmed = rawUrl.trim()
        if (trimmed.isEmpty()) return ""
        if (!trimmed.startsWith("http://", ignoreCase = true) && !trimmed.startsWith("https://", ignoreCase = true)) {
            trimmed = "http://$trimmed"
        }
        return trimmed.trimEnd('/')
    }

    fun validateUrl(rawUrl: String): String? {
        val trimmed = rawUrl.trim()
        if (trimmed.isEmpty()) {
            return "Please enter your PC's Mesh REST URL (e.g. http://192.168.1.X:8766)."
        }
        val lower = trimmed.lowercase()
        if (lower.contains("localhost") || lower.contains("127.0.0.1")) {
            return "Cannot use 'localhost' or '127.0.0.1' from your phone. Run 'ipconfig' in Windows Command Prompt on your PC and enter its LAN IPv4 address (e.g. http://192.168.1.X:8766)."
        }
        return null
    }

    suspend fun getStatus(baseUrl: String): ApiResult<MeshStatus> = withContext(Dispatchers.IO) {
        val validationErr = validateUrl(baseUrl)
        if (validationErr != null) {
            return@withContext ApiResult.Error(validationErr)
        }

        val normalized = normalizeUrl(baseUrl)
        val request = try {
            Request.Builder()
                .url("$normalized/status")
                .get()
                .build()
        } catch (e: Exception) {
            return@withContext ApiResult.Error("Invalid URL syntax: ${e.message}")
        }

        try {
            statusClient.newCall(request).execute().use { response ->
                val responseBody = response.body?.string() ?: ""
                if (!response.isSuccessful) {
                    if (response.code == 404) {
                        return@withContext ApiResult.Error(
                            "HTTP 404 (/status not found at $normalized). Ensure you are connecting to port 8766 (Mesh REST API), NOT port 8765 (WebSocket) or port 8000 (FastAPI).",
                            response.code
                        )
                    }
                    val errorDetail = parseErrorMessage(responseBody) ?: "HTTP ${response.code} ${response.message}"
                    return@withContext ApiResult.Error("Laptop error ($errorDetail)", response.code)
                }

                try {
                    val status = statusAdapter.fromJson(responseBody)
                    if (status != null && status.selfId.isNotEmpty()) {
                        ApiResult.Success(status)
                    } else {
                        val json = JSONObject(responseBody)
                        val graphObj = json.optJSONObject("graph")
                        val graphMap = mutableMapOf<String, MeshNodeInfo>()
                        if (graphObj != null) {
                            val keys = graphObj.keys()
                            while (keys.hasNext()) {
                                val k = keys.next()
                                val nodeObj = graphObj.optJSONObject(k)
                                if (nodeObj != null) {
                                    val neighborsList = mutableListOf<String>()
                                    val nArr = nodeObj.optJSONArray("neighbors")
                                    if (nArr != null) {
                                        for (i in 0 until nArr.length()) {
                                            neighborsList.add(nArr.optString(i))
                                        }
                                    }
                                    graphMap[k] = MeshNodeInfo(
                                        addr = nodeObj.optString("addr"),
                                        name = nodeObj.optString("name"),
                                        neighbors = neighborsList,
                                        lastSeen = nodeObj.optDouble("last_seen", 0.0)
                                    )
                                }
                            }
                        }

                        val fallback = MeshStatus(
                            selfId = json.optString("self_id", "unknown"),
                            selfName = json.optString("self_name", "Unknown Node"),
                            selfAddr = json.optString("self_addr", ""),
                            advertiseIp = json.optString("advertise_ip", ""),
                            graphVersion = json.optInt("graph_version", 0),
                            graph = graphMap
                        )
                        ApiResult.Success(fallback)
                    }
                } catch (e: Exception) {
                    ApiResult.Error("Failed to parse laptop status response: ${e.message}")
                }
            }
        } catch (e: Exception) {
            ApiResult.Error(classifyNetworkException(e, normalized))
        }
    }

    suspend fun setNodeName(baseUrl: String, name: String): ApiResult<Unit> = withContext(Dispatchers.IO) {
        val normalized = normalizeUrl(baseUrl)
        val payload = JSONObject().apply { put("name", name.trim()) }.toString()
        val request = Request.Builder()
            .url("$normalized/name")
            .post(payload.toRequestBody(jsonMediaType))
            .build()
        try {
            statusClient.newCall(request).execute().use { response ->
                if (response.isSuccessful) ApiResult.Success(Unit)
                else ApiResult.Error("Failed to save name: HTTP ${response.code}")
            }
        } catch (e: Exception) {
            ApiResult.Error(classifyNetworkException(e, normalized))
        }
    }

    suspend fun connectPeer(baseUrl: String, peerUrl: String): ApiResult<Unit> = withContext(Dispatchers.IO) {
        val normalized = normalizeUrl(baseUrl)
        val payload = JSONObject().apply { put("url", peerUrl.trim()) }.toString()
        val request = Request.Builder()
            .url("$normalized/connect")
            .post(payload.toRequestBody(jsonMediaType))
            .build()
        try {
            statusClient.newCall(request).execute().use { response ->
                if (response.isSuccessful) ApiResult.Success(Unit)
                else {
                    val body = response.body?.string() ?: ""
                    ApiResult.Error(parseErrorMessage(body) ?: "HTTP ${response.code}")
                }
            }
        } catch (e: Exception) {
            ApiResult.Error(classifyNetworkException(e, normalized))
        }
    }

    suspend fun getMeshMessages(baseUrl: String): ApiResult<Pair<List<MeshMessageItem>, List<MeshMessageItem>>> = withContext(Dispatchers.IO) {
        val normalized = normalizeUrl(baseUrl)
        try {
            val inboxReq = Request.Builder().url("$normalized/inbox").get().build()
            val sentReq = Request.Builder().url("$normalized/sent").get().build()

            val inbox = statusClient.newCall(inboxReq).execute().use { res ->
                val body = res.body?.string() ?: "[]"
                parseMessageList(body)
            }
            val sent = statusClient.newCall(sentReq).execute().use { res ->
                val body = res.body?.string() ?: "[]"
                parseMessageList(body)
            }
            ApiResult.Success(Pair(inbox, sent))
        } catch (e: Exception) {
            ApiResult.Error(classifyNetworkException(e, normalized))
        }
    }

    private fun parseMessageList(jsonStr: String): List<MeshMessageItem> {
        return try {
            messageListAdapter.fromJson(jsonStr) ?: emptyList()
        } catch (_: Exception) {
            val list = mutableListOf<MeshMessageItem>()
            try {
                val arr = JSONArray(jsonStr)
                for (i in 0 until arr.length()) {
                    val obj = arr.optJSONObject(i) ?: continue
                    list.add(
                        MeshMessageItem(
                            from = obj.optString("from").takeIf { it.isNotEmpty() },
                            to = obj.optString("to").takeIf { it.isNotEmpty() },
                            msg = obj.optString("msg", ""),
                            ts = obj.optDouble("ts", 0.0)
                        )
                    )
                }
            } catch (_: Exception) {}
            list
        }
    }

    suspend fun sendMeshMessage(baseUrl: String, dest: String, msg: String): ApiResult<Unit> = withContext(Dispatchers.IO) {
        val normalized = normalizeUrl(baseUrl)
        val payload = JSONObject().apply {
            put("dest", dest)
            put("msg", msg)
        }.toString()
        val request = Request.Builder()
            .url("$normalized/send")
            .post(payload.toRequestBody(jsonMediaType))
            .build()
        try {
            statusClient.newCall(request).execute().use { response ->
                val body = response.body?.string() ?: ""
                if (response.isSuccessful) {
                    val obj = JSONObject(body)
                    if (obj.has("error")) {
                        ApiResult.Error(obj.optString("error"))
                    } else {
                        ApiResult.Success(Unit)
                    }
                } else {
                    ApiResult.Error(parseErrorMessage(body) ?: "HTTP ${response.code}")
                }
            }
        } catch (e: Exception) {
            ApiResult.Error(classifyNetworkException(e, normalized))
        }
    }

    suspend fun sendPrompt(
        baseUrl: String,
        bearerToken: String,
        promptText: String
    ): ApiResult<PromptResponse> = withContext(Dispatchers.IO) {
        val validationErr = validateUrl(baseUrl)
        if (validationErr != null) {
            return@withContext ApiResult.Error(validationErr)
        }
        val normalized = normalizeUrl(baseUrl)

        if (promptText.trim().isEmpty()) {
            return@withContext ApiResult.Error("Prompt cannot be empty.")
        }

        val trimmedToken = bearerToken.trim()
        if (trimmedToken.isEmpty()) {
            return@withContext ApiResult.Error(
                "Missing Bearer Token: Prompt execution requires a shared secret token. Configure MESH_PROMPT_TOKEN in your laptop's .env file, and enter the identical token in app Settings."
            )
        }

        val jsonPayload = JSONObject().apply {
            put("prompt", promptText.trim())
        }.toString()

        val requestBuilder = try {
            Request.Builder()
                .url("$normalized/prompt")
                .header("Authorization", "Bearer $trimmedToken")
                .post(jsonPayload.toRequestBody(jsonMediaType))
        } catch (e: Exception) {
            return@withContext ApiResult.Error("Invalid URL syntax: ${e.message}")
        }

        val request = requestBuilder.build()

        try {
            promptClient.newCall(request).execute().use { response ->
                val responseBody = response.body?.string() ?: ""

                if (response.code == 401) {
                    return@withContext ApiResult.Error(
                        "Unauthorized (401): Missing or malformed Bearer token in request header. Expected 'Authorization: Bearer <token>'",
                        response.code
                    )
                }
                if (response.code == 403) {
                    return@withContext ApiResult.Error(
                        "Access Denied (403): Invalid Bearer token. Ensure the token in app Settings matches MESH_PROMPT_TOKEN configured in your laptop's .env file.",
                        response.code
                    )
                }
                if (response.code == 503) {
                    val detail = parseErrorMessage(responseBody)
                        ?: "MESH_PROMPT_TOKEN is not configured on the laptop. Please set MESH_PROMPT_TOKEN in your laptop's .env file before sending prompts."
                    return@withContext ApiResult.Error("Service Unavailable (503): $detail", response.code)
                }

                if (!response.isSuccessful) {
                    val errorDetail = parseErrorMessage(responseBody)
                        ?: "HTTP ${response.code}: ${response.message}"
                    return@withContext ApiResult.Error("Prompt execution failed ($errorDetail)", response.code)
                }

                try {
                    val json = JSONObject(responseBody)
                    val success = json.optBoolean("success", true)
                    val outputText = json.optString("response", "")
                    val err = json.optString("error", "")

                    if (!success && err.isNotEmpty()) {
                        ApiResult.Error("Agent error: $err", response.code)
                    } else {
                        ApiResult.Success(PromptResponse(success = true, response = outputText))
                    }
                } catch (e: Exception) {
                    ApiResult.Success(PromptResponse(success = true, response = responseBody))
                }
            }
        } catch (e: Exception) {
            ApiResult.Error(classifyNetworkException(e, normalized))
        }
    }

    private fun parseErrorMessage(body: String): String? {
        if (body.isBlank()) return null
        return try {
            val json = JSONObject(body)
            json.optString("error").takeIf { it.isNotEmpty() }
                ?: json.optString("detail").takeIf { it.isNotEmpty() }
                ?: json.optString("message").takeIf { it.isNotEmpty() }
        } catch (_: Exception) {
            body.take(150)
        }
    }

    fun classifyNetworkException(e: Exception, url: String): String {
        val msg = e.message ?: ""
        return when {
            e is UnknownHostException -> {
                "Unknown host '$url'. Check the IP address in Settings. Run 'ipconfig' on Windows to find your PC's Wi-Fi IPv4 address (e.g. 192.168.1.42)."
            }
            e is ConnectException -> {
                "Connection refused to '$url'. The PC was reached, but no server is listening on port 8766.\nEnsure your PC server is running:\npython mesh\\server.py --port 8765\n(Note: REST API listens on port 8766 = port + 1)."
            }
            e is NoRouteToHostException -> {
                "No route to host '$url'. Phone and PC cannot communicate. Verify:\n1) Both devices are on the exact same Wi-Fi network.\n2) Your router does not have 'AP Isolation' or 'Guest Mode' enabled."
            }
            e is SocketTimeoutException -> {
                "Connection timed out reaching '$url'. Possible causes:\n1) Windows Defender Firewall is blocking inbound port 8766 (run allow_mesh_firewall.bat as Administrator on your PC).\n2) Router AP Isolation prevents LAN communication.\n3) Wrong PC IP address (verify with 'ipconfig')."
            }
            msg.contains("Cleartext", ignoreCase = true) -> {
                "Cleartext HTTP traffic was rejected by Android security policy."
            }
            else -> "Network failure (${e.javaClass.simpleName}): ${e.localizedMessage ?: "Unknown network error"}"
        }
    }
}
