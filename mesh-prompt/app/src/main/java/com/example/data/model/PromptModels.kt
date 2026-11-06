package com.example.data.model

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class PromptRequest(
    @Json(name = "prompt") val prompt: String
)

@JsonClass(generateAdapter = true)
data class PromptResponse(
    @Json(name = "success") val success: Boolean = false,
    @Json(name = "response") val response: String? = null,
    @Json(name = "error") val error: String? = null
)
