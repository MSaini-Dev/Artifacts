package com.example

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import com.example.ui.PromptScreen
import com.example.ui.PromptViewModel
import com.example.ui.theme.MyApplicationTheme

class MainActivity : ComponentActivity() {
    private val viewModel: PromptViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MyApplicationTheme {
                val state by viewModel.uiState.collectAsState()
                PromptScreen(
                    state = state,
                    onBaseUrlChange = viewModel::updateBaseUrl,
                    onBearerTokenChange = viewModel::updateBearerToken,
                    onPromptChange = viewModel::updatePromptInput,
                    onThisNodeNameChange = viewModel::updateThisNodeNameInput,
                    onPeerUrlChange = viewModel::updatePeerUrlInput,
                    onSaveNodeName = viewModel::saveNodeName,
                    onConnectPeer = viewModel::connectPeer,
                    onSelectNode = viewModel::selectNode,
                    onSetRightPaneMode = viewModel::setRightPaneMode,
                    onSetMobileTab = viewModel::setMobileTab,
                    onSendAction = viewModel::sendAction,
                    onClearResponse = viewModel::clearResponse,
                    onRefreshStatus = viewModel::refreshStatus,
                    onToggleSettings = viewModel::toggleSettingsDialog,
                    onDismissBanner = viewModel::dismissBanner
                )
            }
        }
    }
}
