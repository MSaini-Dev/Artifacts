package com.example.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.data.model.MeshMessageItem
import com.example.data.model.MeshStatus
import com.example.data.network.ApiResult
import com.example.data.network.MeshApiClient
import com.example.data.storage.MeshPreferences
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

enum class RightPaneMode {
    MESSAGE,
    ASK_AGENT
}

enum class MobileScreenTab {
    GRAPH,
    CHAT
}

enum class NetworkInterfaceType {
    WIFI,
    BLUETOOTH_PAN,
    LOCALHOST,
    CUSTOM
}

sealed class ConnectionState {
    data object Idle : ConnectionState()
    data object Testing : ConnectionState()
    data class Connected(val status: MeshStatus) : ConnectionState()
    data class Error(val message: String) : ConnectionState()
}

data class MeshUiState(
    val baseUrl: String = "",
    val bearerToken: String = "",
    val connectionState: ConnectionState = ConnectionState.Idle,
    val meshStatus: MeshStatus? = null,
    val selectedNodeId: String? = null,
    val rightPaneMode: RightPaneMode = RightPaneMode.ASK_AGENT,
    val mobileTab: MobileScreenTab = MobileScreenTab.GRAPH,
    val thisNodeNameInput: String = "",
    val peerUrlInput: String = "ws://",
    val promptInput: String = "",
    val isExecutingPrompt: Boolean = false,
    val executionDurationSeconds: Long = 0,
    val lastResponse: String? = null,
    val lastError: String? = null,
    val executionSuccess: Boolean? = null,
    val lastExecutionTimeMs: Long? = null,
    val messages: List<MeshMessageItem> = emptyList(),
    val isSendingMessage: Boolean = false,
    val isSavingName: Boolean = false,
    val isConnectingPeer: Boolean = false,
    val bannerMessage: String? = null,
    val showSettingsDialog: Boolean = false
) {
    val interfaceType: NetworkInterfaceType
        get() = when {
            baseUrl.contains("192.168.44.") || baseUrl.contains("bluetooth", ignoreCase = true) -> NetworkInterfaceType.BLUETOOTH_PAN
            baseUrl.contains("10.0.2.2") || baseUrl.contains("127.0.0.1") || baseUrl.contains("localhost") -> NetworkInterfaceType.LOCALHOST
            baseUrl.contains("192.168.") || baseUrl.contains("10.") || baseUrl.contains("172.") -> NetworkInterfaceType.WIFI
            else -> NetworkInterfaceType.CUSTOM
        }
}

class PromptViewModel(application: Application) : AndroidViewModel(application) {
    private val preferences = MeshPreferences(application)
    private val apiClient = MeshApiClient()

    private val _uiState = MutableStateFlow(
        MeshUiState(
            baseUrl = preferences.baseUrl,
            bearerToken = preferences.bearerToken,
            promptInput = preferences.lastPrompt
        )
    )
    val uiState: StateFlow<MeshUiState> = _uiState.asStateFlow()

    private var pollJob: Job? = null
    private var timerJob: Job? = null

    init {
        if (_uiState.value.baseUrl.isNotBlank()) {
            refreshStatus()
        }
        startPolling()
    }

    private fun startPolling() {
        pollJob?.cancel()
        pollJob = viewModelScope.launch {
            while (isActive) {
                delay(4000)
                val currentUrl = _uiState.value.baseUrl
                if (currentUrl.isNotBlank() && !_uiState.value.isExecutingPrompt) {
                    val res = apiClient.getStatus(currentUrl)
                    if (res is ApiResult.Success) {
                        _uiState.update { current ->
                            val status = res.data
                            val sel = current.selectedNodeId ?: status.selfId
                            current.copy(
                                connectionState = ConnectionState.Connected(status),
                                meshStatus = status,
                                selectedNodeId = sel,
                                thisNodeNameInput = if (current.isSavingName) current.thisNodeNameInput else status.selfName
                            )
                        }
                    }
                }
            }
        }
    }

    fun updateBaseUrl(newUrl: String) {
        val sanitized = newUrl.replace("\n", "").trim()
        _uiState.update { it.copy(baseUrl = sanitized) }
        preferences.baseUrl = sanitized
    }

    fun updateBearerToken(newToken: String) {
        val sanitized = newToken.replace("\n", "").trim()
        _uiState.update { it.copy(bearerToken = sanitized) }
        preferences.bearerToken = sanitized
    }

    fun updatePromptInput(text: String) {
        _uiState.update { it.copy(promptInput = text) }
        preferences.lastPrompt = text
    }

    fun updateThisNodeNameInput(name: String) {
        _uiState.update { it.copy(thisNodeNameInput = name) }
    }

    fun updatePeerUrlInput(url: String) {
        _uiState.update { it.copy(peerUrlInput = url) }
    }

    fun setRightPaneMode(mode: RightPaneMode) {
        _uiState.update { it.copy(rightPaneMode = mode) }
        if (mode == RightPaneMode.MESSAGE) {
            refreshMessages()
        }
    }

    fun setMobileTab(tab: MobileScreenTab) {
        _uiState.update { it.copy(mobileTab = tab) }
    }

    fun selectNode(nodeId: String) {
        _uiState.update { it.copy(selectedNodeId = nodeId, mobileTab = MobileScreenTab.CHAT) }
    }

    fun toggleSettingsDialog(show: Boolean) {
        _uiState.update { it.copy(showSettingsDialog = show) }
    }

    fun dismissBanner() {
        _uiState.update { it.copy(bannerMessage = null) }
    }

    fun refreshStatus() {
        val currentUrl = _uiState.value.baseUrl
        if (currentUrl.isBlank()) {
            _uiState.update {
                it.copy(
                    connectionState = ConnectionState.Error("Please configure your PC's Mesh REST base URL in Settings (e.g. http://192.168.1.X:8766). Run 'ipconfig' in Windows Command Prompt to find your PC's IPv4 address.")
                )
            }
            return
        }

        viewModelScope.launch {
            _uiState.update { it.copy(connectionState = ConnectionState.Testing) }
            val result = apiClient.getStatus(currentUrl)
            when (result) {
                is ApiResult.Success -> {
                    val status = result.data
                    _uiState.update {
                        it.copy(
                            connectionState = ConnectionState.Connected(status),
                            meshStatus = status,
                            thisNodeNameInput = status.selfName,
                            selectedNodeId = it.selectedNodeId ?: status.selfId,
                            bannerMessage = null
                        )
                    }
                }
                is ApiResult.Error -> {
                    _uiState.update {
                        it.copy(
                            connectionState = ConnectionState.Error(result.message),
                            bannerMessage = result.message
                        )
                    }
                }
            }
        }
    }

    fun saveNodeName() {
        val name = _uiState.value.thisNodeNameInput.trim()
        if (name.isEmpty()) return

        viewModelScope.launch {
            _uiState.update { it.copy(isSavingName = true) }
            val result = apiClient.setNodeName(_uiState.value.baseUrl, name)
            _uiState.update { it.copy(isSavingName = false) }
            if (result is ApiResult.Success) {
                refreshStatus()
            } else if (result is ApiResult.Error) {
                _uiState.update { it.copy(bannerMessage = result.message) }
            }
        }
    }

    fun connectPeer() {
        val peerUrl = _uiState.value.peerUrlInput.trim()
        if (peerUrl.isEmpty() || peerUrl == "ws://") return

        viewModelScope.launch {
            _uiState.update { it.copy(isConnectingPeer = true) }
            val result = apiClient.connectPeer(_uiState.value.baseUrl, peerUrl)
            _uiState.update { it.copy(isConnectingPeer = false) }
            if (result is ApiResult.Success) {
                _uiState.update { it.copy(peerUrlInput = "ws://", bannerMessage = "Dialing peer: $peerUrl") }
                refreshStatus()
            } else if (result is ApiResult.Error) {
                _uiState.update { it.copy(bannerMessage = result.message) }
            }
        }
    }

    fun refreshMessages() {
        viewModelScope.launch {
            val result = apiClient.getMeshMessages(_uiState.value.baseUrl)
            if (result is ApiResult.Success) {
                val (inbox, sent) = result.data
                val all = (inbox + sent).sortedBy { it.ts }
                _uiState.update { it.copy(messages = all) }
            }
        }
    }

    fun sendAction() {
        val mode = _uiState.value.rightPaneMode
        if (mode == RightPaneMode.ASK_AGENT) {
            sendPrompt()
        } else {
            sendChatMessage()
        }
    }

    private fun sendChatMessage() {
        val text = _uiState.value.promptInput.trim()
        val dest = _uiState.value.selectedNodeId ?: _uiState.value.meshStatus?.selfId
        if (text.isEmpty() || dest == null) return

        viewModelScope.launch {
            _uiState.update { it.copy(isSendingMessage = true) }
            val result = apiClient.sendMeshMessage(_uiState.value.baseUrl, dest, text)
            _uiState.update { it.copy(isSendingMessage = false) }
            if (result is ApiResult.Success) {
                _uiState.update { it.copy(promptInput = "") }
                refreshMessages()
            } else if (result is ApiResult.Error) {
                _uiState.update { it.copy(bannerMessage = result.message) }
            }
        }
    }

    private fun sendPrompt() {
        val currentState = _uiState.value
        if (currentState.isExecutingPrompt) return

        val prompt = currentState.promptInput.trim()
        if (prompt.isEmpty()) {
            _uiState.update { it.copy(lastError = "Prompt cannot be empty.", executionSuccess = false) }
            return
        }

        val baseUrl = currentState.baseUrl.trim()
        if (baseUrl.isEmpty()) {
            _uiState.update { it.copy(lastError = "Please specify the laptop Mesh REST URL.", executionSuccess = false) }
            return
        }

        viewModelScope.launch {
            _uiState.update {
                it.copy(
                    isExecutingPrompt = true,
                    executionDurationSeconds = 0,
                    lastResponse = null,
                    lastError = null,
                    executionSuccess = null
                )
            }

            timerJob?.cancel()
            val startTime = System.currentTimeMillis()
            timerJob = launch {
                while (true) {
                    delay(1000)
                    val elapsed = (System.currentTimeMillis() - startTime) / 1000
                    _uiState.update { it.copy(executionDurationSeconds = elapsed) }
                }
            }

            val token = currentState.bearerToken.trim()
            val result = apiClient.sendPrompt(baseUrl, token, prompt)
            val durationMs = System.currentTimeMillis() - startTime
            timerJob?.cancel()

            when (result) {
                is ApiResult.Success -> {
                    _uiState.update {
                        it.copy(
                            isExecutingPrompt = false,
                            lastResponse = result.data.response ?: "(Empty response received)",
                            lastError = null,
                            executionSuccess = true,
                            lastExecutionTimeMs = durationMs
                        )
                    }
                }
                is ApiResult.Error -> {
                    _uiState.update {
                        it.copy(
                            isExecutingPrompt = false,
                            lastResponse = null,
                            lastError = result.message,
                            executionSuccess = false,
                            lastExecutionTimeMs = durationMs
                        )
                    }
                }
            }
        }
    }

    fun clearResponse() {
        _uiState.update {
            it.copy(
                lastResponse = null,
                lastError = null,
                executionSuccess = null,
                lastExecutionTimeMs = null
            )
        }
    }

    override fun onCleared() {
        super.onCleared()
        pollJob?.cancel()
        timerJob?.cancel()
    }
}
