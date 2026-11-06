package com.example.data.model

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class MeshNodeInfo(
    @Json(name = "addr") val addr: String = "",
    @Json(name = "name") val name: String = "",
    @Json(name = "neighbors") val neighbors: List<String> = emptyList(),
    @Json(name = "last_seen") val lastSeen: Double = 0.0
)

@JsonClass(generateAdapter = true)
data class MeshStatus(
    @Json(name = "self_id") val selfId: String = "",
    @Json(name = "self_name") val selfName: String = "",
    @Json(name = "self_addr") val selfAddr: String = "",
    @Json(name = "advertise_ip") val advertiseIp: String = "",
    @Json(name = "graph_version") val graphVersion: Int = 0,
    @Json(name = "direct_peers") val directPeers: List<String> = emptyList(),
    @Json(name = "online_peers") val onlinePeers: List<String> = emptyList(),
    @Json(name = "graph") val graph: Map<String, MeshNodeInfo> = emptyMap()
)

@JsonClass(generateAdapter = true)
data class MeshMessageItem(
    @Json(name = "from") val from: String? = null,
    @Json(name = "to") val to: String? = null,
    @Json(name = "msg") val msg: String = "",
    @Json(name = "ts") val ts: Double = 0.0
)
