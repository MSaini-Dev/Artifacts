package com.example.data.storage

import android.content.Context
import android.content.SharedPreferences

class MeshPreferences(context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    var baseUrl: String
        get() = prefs.getString(KEY_BASE_URL, DEFAULT_URL) ?: DEFAULT_URL
        set(value) = prefs.edit().putString(KEY_BASE_URL, value.trim()).apply()

    var bearerToken: String
        get() = prefs.getString(KEY_BEARER_TOKEN, "") ?: ""
        set(value) = prefs.edit().putString(KEY_BEARER_TOKEN, value.trim()).apply()

    var lastPrompt: String
        get() = prefs.getString(KEY_LAST_PROMPT, "") ?: ""
        set(value) = prefs.edit().putString(KEY_LAST_PROMPT, value).apply()

    companion object {
        private const val PREFS_NAME = "mesh_remote_prompt_prefs"
        private const val KEY_BASE_URL = "base_url"
        private const val KEY_BEARER_TOKEN = "bearer_token"
        private const val KEY_LAST_PROMPT = "last_prompt"
        const val DEFAULT_URL = ""
    }
}
