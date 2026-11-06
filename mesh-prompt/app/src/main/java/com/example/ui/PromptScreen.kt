package com.example.ui

import android.widget.Toast
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.ui.text.TextStyle
import androidx.compose.foundation.layout.widthIn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Bluetooth
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.ErrorOutline
import androidx.compose.material.icons.filled.Hub
import androidx.compose.material.icons.filled.Key
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.SmartToy
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material.icons.filled.Wifi
import androidx.compose.material.icons.outlined.ChatBubbleOutline
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.TabRowDefaults
import androidx.compose.material3.TabRowDefaults.tabIndicatorOffset
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.data.model.MeshMessageItem
import com.example.ui.components.MeshGraphCanvas
import com.example.ui.theme.MeshBg
import com.example.ui.theme.MeshBlue
import com.example.ui.theme.MeshFg
import com.example.ui.theme.MeshGreen
import com.example.ui.theme.MeshInputBg
import com.example.ui.theme.MeshLine
import com.example.ui.theme.MeshMuted
import com.example.ui.theme.MeshPanel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PromptScreen(
    state: MeshUiState,
    onBaseUrlChange: (String) -> Unit,
    onBearerTokenChange: (String) -> Unit,
    onPromptChange: (String) -> Unit,
    onThisNodeNameChange: (String) -> Unit,
    onPeerUrlChange: (String) -> Unit,
    onSaveNodeName: () -> Unit,
    onConnectPeer: () -> Unit,
    onSelectNode: (String) -> Unit,
    onSetRightPaneMode: (RightPaneMode) -> Unit,
    onSetMobileTab: (MobileScreenTab) -> Unit,
    onSendAction: () -> Unit,
    onClearResponse: () -> Unit,
    onRefreshStatus: () -> Unit,
    onToggleSettings: (Boolean) -> Unit,
    onDismissBanner: () -> Unit,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val clipboardManager = LocalClipboardManager.current

    Scaffold(
        modifier = modifier
            .fillMaxSize()
            .background(MeshBg)
            .imePadding(),
        contentWindowInsets = WindowInsets.safeDrawing,
        topBar = {
            MeshTopBar(
                state = state,
                onRefresh = onRefreshStatus,
                onOpenSettings = { onToggleSettings(true) }
            )
        }
    ) { innerPadding ->
        BoxWithConstraints(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .background(MeshBg)
        ) {
            val isWideScreen = maxWidth >= 700.dp

            if (isWideScreen) {
                // DESKTOP SPLIT VIEW (Side-by-side panes)
                Row(modifier = Modifier.fillMaxSize()) {
                    // Left Pane: Mesh Network Graph
                    Box(
                        modifier = Modifier
                            .weight(1f)
                            .fillMaxHeight()
                            .border(width = 1.dp, color = MeshLine)
                    ) {
                        LeftMeshPane(
                            state = state,
                            onThisNodeNameChange = onThisNodeNameChange,
                            onSaveNodeName = onSaveNodeName,
                            onPeerUrlChange = onPeerUrlChange,
                            onConnectPeer = onConnectPeer,
                            onSelectNode = onSelectNode
                        )
                    }

                    // Right Pane: Dedicated Assistant Chat & Messaging
                    Box(
                        modifier = Modifier
                            .weight(1f)
                            .fillMaxHeight()
                            .background(MeshPanel)
                    ) {
                        RightChatPane(
                            state = state,
                            onSetMode = onSetRightPaneMode,
                            onPromptChange = onPromptChange,
                            onSend = onSendAction,
                            onClearResponse = onClearResponse,
                            onCopyText = { text ->
                                clipboardManager.setText(AnnotatedString(text))
                                Toast.makeText(context, "Copied to clipboard", Toast.LENGTH_SHORT).show()
                            }
                        )
                    }
                }
            } else {
                // MOBILE VIEW (Tabbed Layout: Graph vs Chat)
                Column(modifier = Modifier.fillMaxSize()) {
                    // Inline Banner Notification (never obscures navigation tabs)
                    if (state.bannerMessage != null) {
                        BannerNotification(
                            message = state.bannerMessage,
                            onDismiss = onDismissBanner
                        )
                    }

                    TabRow(
                        selectedTabIndex = if (state.mobileTab == MobileScreenTab.GRAPH) 0 else 1,
                        containerColor = MeshPanel,
                        contentColor = MeshFg,
                        indicator = { tabPositions ->
                            TabRowDefaults.SecondaryIndicator(
                                Modifier.tabIndicatorOffset(tabPositions[if (state.mobileTab == MobileScreenTab.GRAPH) 0 else 1]),
                                color = MeshGreen
                            )
                        },
                        divider = { HorizontalDivider(color = MeshLine) }
                    ) {
                        val peerCount = state.meshStatus?.graph?.size?.minus(1)?.coerceAtLeast(0) ?: 0
                        Tab(
                            selected = state.mobileTab == MobileScreenTab.GRAPH,
                            onClick = { onSetMobileTab(MobileScreenTab.GRAPH) },
                            text = {
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.Hub,
                                        contentDescription = null,
                                        modifier = Modifier.size(16.dp),
                                        tint = if (state.mobileTab == MobileScreenTab.GRAPH) MeshGreen else MeshMuted
                                    )
                                    Text(
                                        text = "Mesh Network",
                                        fontWeight = if (state.mobileTab == MobileScreenTab.GRAPH) FontWeight.Bold else FontWeight.Normal,
                                        color = if (state.mobileTab == MobileScreenTab.GRAPH) MeshFg else MeshMuted
                                    )
                                }
                            }
                        )
                        Tab(
                            selected = state.mobileTab == MobileScreenTab.CHAT,
                            onClick = { onSetMobileTab(MobileScreenTab.CHAT) },
                            text = {
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                                ) {
                                    Icon(
                                        imageVector = if (state.rightPaneMode == RightPaneMode.ASK_AGENT) Icons.Default.SmartToy else Icons.Outlined.ChatBubbleOutline,
                                        contentDescription = null,
                                        modifier = Modifier.size(16.dp),
                                        tint = if (state.mobileTab == MobileScreenTab.CHAT) MeshBlue else MeshMuted
                                    )
                                    Text(
                                        text = if (state.rightPaneMode == RightPaneMode.ASK_AGENT) "Ask Agent" else "Messages",
                                        fontWeight = if (state.mobileTab == MobileScreenTab.CHAT) FontWeight.Bold else FontWeight.Normal,
                                        color = if (state.mobileTab == MobileScreenTab.CHAT) MeshFg else MeshMuted
                                    )
                                }
                            }
                        )
                    }

                    Box(modifier = Modifier.weight(1f)) {
                        when (state.mobileTab) {
                            MobileScreenTab.GRAPH -> {
                                LeftMeshPane(
                                    state = state,
                                    onThisNodeNameChange = onThisNodeNameChange,
                                    onSaveNodeName = onSaveNodeName,
                                    onPeerUrlChange = onPeerUrlChange,
                                    onConnectPeer = onConnectPeer,
                                    onSelectNode = onSelectNode
                                )
                            }
                            MobileScreenTab.CHAT -> {
                                RightChatPane(
                                    state = state,
                                    onSetMode = onSetRightPaneMode,
                                    onPromptChange = onPromptChange,
                                    onSend = onSendAction,
                                    onClearResponse = onClearResponse,
                                    onCopyText = { text ->
                                        clipboardManager.setText(AnnotatedString(text))
                                        Toast.makeText(context, "Copied to clipboard", Toast.LENGTH_SHORT).show()
                                    }
                                )
                            }
                        }
                    }
                }
            }
        }
    }

    // Settings Modal Dialog
    if (state.showSettingsDialog) {
        SettingsDialog(
            baseUrl = state.baseUrl,
            bearerToken = state.bearerToken,
            onBaseUrlChange = onBaseUrlChange,
            onBearerTokenChange = onBearerTokenChange,
            onDismiss = { onToggleSettings(false) },
            onTest = {
                onRefreshStatus()
                onToggleSettings(false)
            }
        )
    }
}

@Composable
fun BannerNotification(
    message: String,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier
) {
    Surface(
        color = Color(0xFF1E293B),
        shape = RoundedCornerShape(8.dp),
        border = CardDefaults.outlinedCardBorder().copy(brush = SolidColor(Color(0xFF334155))),
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 6.dp)
            .clickable { onDismiss() }
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Icon(
                imageVector = Icons.Default.ErrorOutline,
                contentDescription = null,
                tint = Color(0xFF38BDF8),
                modifier = Modifier.size(16.dp)
            )
            Text(
                text = message,
                color = Color(0xFFF1F5F9),
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.weight(1f)
            )
            IconButton(
                onClick = onDismiss,
                modifier = Modifier.size(20.dp)
            ) {
                Icon(
                    imageVector = Icons.Default.Clear,
                    contentDescription = "Dismiss",
                    tint = MeshMuted,
                    modifier = Modifier.size(14.dp)
                )
            }
        }
    }
}

@Composable
fun MeshCompactTextField(
    value: String,
    onValueChange: (String) -> Unit,
    placeholder: String,
    modifier: Modifier = Modifier,
    textStyle: TextStyle = TextStyle(color = MeshFg, fontSize = 12.sp),
    keyboardOptions: KeyboardOptions = KeyboardOptions.Default,
    keyboardActions: KeyboardActions = KeyboardActions.Default
) {
    BasicTextField(
        value = value,
        onValueChange = onValueChange,
        singleLine = true,
        textStyle = textStyle,
        cursorBrush = SolidColor(MeshGreen),
        keyboardOptions = keyboardOptions,
        keyboardActions = keyboardActions,
        modifier = modifier,
        decorationBox = { innerTextField ->
            Box(
                contentAlignment = Alignment.CenterStart,
                modifier = Modifier
                    .fillMaxSize()
                    .padding(horizontal = 8.dp)
            ) {
                if (value.isEmpty()) {
                    Text(
                        text = placeholder,
                        color = MeshMuted,
                        fontSize = textStyle.fontSize,
                        fontFamily = textStyle.fontFamily
                    )
                }
                innerTextField()
            }
        }
    )
}

@Composable
fun MeshTopBar(
    state: MeshUiState,
    onRefresh: () -> Unit,
    onOpenSettings: () -> Unit
) {
    Surface(
        color = MeshBg,
        modifier = Modifier
            .fillMaxWidth()
            .border(width = 1.dp, color = MeshLine)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 10.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            // Left: Logo & Title
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.weight(1f, fill = false)
            ) {
                Box(
                    modifier = Modifier
                        .size(30.dp)
                        .clip(RoundedCornerShape(6.dp))
                        .background(Color(0xFF18181B))
                        .border(1.dp, MeshLine, RoundedCornerShape(6.dp)),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        imageVector = Icons.Default.Hub,
                        contentDescription = "Mesh Logo",
                        tint = MeshGreen,
                        modifier = Modifier.size(16.dp)
                    )
                }
                Column {
                    Text(
                        text = "Mesh",
                        color = MeshFg,
                        style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold),
                        maxLines = 1
                    )
                    Text(
                        text = "Remote Prompt Box",
                        color = MeshMuted,
                        fontSize = 10.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }
            }

            // Right: Network Type, Online/Offline Pill, Refresh, Settings
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(5.dp)
            ) {
                val isConnected = state.connectionState is ConnectionState.Connected
                val dotColor = if (isConnected) MeshGreen else Color(0xFFEF4444)
                val isBt = state.interfaceType == NetworkInterfaceType.BLUETOOTH_PAN

                // Profile tag: Wi-Fi vs Bluetooth
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = if (isBt) Color(0xFF172554) else Color(0xFF18181B),
                    border = CardDefaults.outlinedCardBorder().copy(
                        brush = SolidColor(if (isBt) Color(0xFF38BDF8) else MeshLine)
                    )
                ) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(3.dp),
                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 3.dp)
                    ) {
                        Icon(
                            imageVector = if (isBt) Icons.Default.Bluetooth else Icons.Default.Wifi,
                            contentDescription = null,
                            tint = if (isBt) Color(0xFF38BDF8) else MeshGreen,
                            modifier = Modifier.size(11.dp)
                        )
                        Text(
                            text = if (isBt) "BT" else "Wi-Fi",
                            color = if (isBt) Color(0xFFE0F2FE) else Color(0xFFA7F3D0),
                            fontSize = 10.sp,
                            fontWeight = FontWeight.Medium,
                            maxLines = 1
                        )
                    }
                }

                // Online/Offline status pill
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = Color(0xFF18181B),
                    border = CardDefaults.outlinedCardBorder().copy(brush = SolidColor(MeshLine))
                ) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(4.dp),
                        modifier = Modifier.padding(horizontal = 7.dp, vertical = 3.dp)
                    ) {
                        Box(
                            modifier = Modifier
                                .size(6.dp)
                                .clip(CircleShape)
                                .background(dotColor)
                        )
                        Text(
                            text = if (isConnected) "Connected" else "Offline",
                            color = if (isConnected) Color(0xFFA7F3D0) else Color(0xFFFCA5A5),
                            fontSize = 10.sp,
                            fontWeight = FontWeight.SemiBold,
                            maxLines = 1
                        )
                    }
                }

                IconButton(
                    onClick = onRefresh,
                    modifier = Modifier.size(32.dp)
                ) {
                    Icon(
                        imageVector = Icons.Default.Refresh,
                        contentDescription = "Refresh",
                        tint = MeshMuted,
                        modifier = Modifier.size(16.dp)
                    )
                }

                IconButton(
                    onClick = onOpenSettings,
                    modifier = Modifier.size(32.dp)
                ) {
                    Icon(
                        imageVector = Icons.Default.Settings,
                        contentDescription = "Settings",
                        tint = MeshMuted,
                        modifier = Modifier.size(16.dp)
                    )
                }
            }
        }
    }
}

@Composable
fun LeftMeshPane(
    state: MeshUiState,
    onThisNodeNameChange: (String) -> Unit,
    onSaveNodeName: () -> Unit,
    onPeerUrlChange: (String) -> Unit,
    onConnectPeer: () -> Unit,
    onSelectNode: (String) -> Unit
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MeshBg)
    ) {
        // 1. Top bar: "This node [Mohit-1173] [Save]" and "[● 0 peers]"
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 14.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.weight(1f)
            ) {
                Text(
                    text = "This node",
                    color = MeshMuted,
                    fontSize = 12.sp
                )
                Box(
                    modifier = Modifier
                        .weight(1f, fill = false)
                        .widthIn(min = 100.dp, max = 150.dp)
                        .height(34.dp)
                        .clip(RoundedCornerShape(8.dp))
                        .background(MeshInputBg)
                        .border(1.dp, MeshLine, RoundedCornerShape(8.dp))
                ) {
                    MeshCompactTextField(
                        value = state.thisNodeNameInput,
                        onValueChange = onThisNodeNameChange,
                        placeholder = "e.g. Mohit-1173",
                        textStyle = MaterialTheme.typography.bodySmall.copy(color = MeshFg, fontWeight = FontWeight.SemiBold)
                    )
                }
                Button(
                    onClick = onSaveNodeName,
                    enabled = !state.isSavingName,
                    shape = RoundedCornerShape(8.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Color(0xFF1C1C1C),
                        contentColor = MeshFg
                    ),
                    modifier = Modifier
                        .height(34.dp)
                        .border(1.dp, MeshLine, RoundedCornerShape(8.dp))
                ) {
                    if (state.isSavingName) {
                        CircularProgressIndicator(modifier = Modifier.size(12.dp), strokeWidth = 2.dp, color = MeshFg)
                    } else {
                        Text("Save", fontSize = 12.sp)
                    }
                }
            }

            // Peer count indicator
            val peerCount = state.meshStatus?.graph?.size?.minus(1)?.coerceAtLeast(0) ?: 0
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(5.dp),
                modifier = Modifier
                    .clip(RoundedCornerShape(12.dp))
                    .background(Color(0xFF141414))
                    .border(1.dp, MeshLine, RoundedCornerShape(12.dp))
                    .padding(horizontal = 8.dp, vertical = 4.dp)
            ) {
                Box(
                    modifier = Modifier
                        .size(6.dp)
                        .clip(CircleShape)
                        .background(if (peerCount > 0) MeshGreen else Color(0xFF71717A))
                )
                Text(
                    text = "$peerCount peers",
                    color = if (peerCount > 0) Color(0xFFA7F3D0) else MeshMuted,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Medium
                )
            }
        }

        HorizontalDivider(color = MeshLine)

        // 2. Interactive Graph Canvas
        Box(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
        ) {
            MeshGraphCanvas(
                status = state.meshStatus,
                selectedNodeId = state.selectedNodeId,
                onSelectNode = onSelectNode
            )
        }

        HorizontalDivider(color = MeshLine)

        // 3. Bottom Peer Connect Bar: "ws://peer-laptop-ip:8765" [+]
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .background(MeshBg)
                .padding(horizontal = 14.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Box(
                    modifier = Modifier
                        .weight(1f)
                        .height(38.dp)
                        .clip(RoundedCornerShape(8.dp))
                        .background(MeshInputBg)
                        .border(1.dp, MeshLine, RoundedCornerShape(8.dp))
                ) {
                    MeshCompactTextField(
                        value = state.peerUrlInput,
                        onValueChange = onPeerUrlChange,
                        placeholder = "ws://peer-laptop-ip:8765",
                        textStyle = MaterialTheme.typography.bodySmall.copy(color = MeshFg, fontFamily = FontFamily.Monospace)
                    )
                }

                Button(
                    onClick = onConnectPeer,
                    enabled = !state.isConnectingPeer,
                    shape = RoundedCornerShape(8.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Color(0xFF1C1C1C),
                        contentColor = MeshFg
                    ),
                    modifier = Modifier
                        .size(38.dp)
                        .border(1.dp, MeshLine, RoundedCornerShape(8.dp)),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(0.dp)
                ) {
                    if (state.isConnectingPeer) {
                        CircularProgressIndicator(modifier = Modifier.size(14.dp), strokeWidth = 2.dp, color = MeshFg)
                    } else {
                        Icon(imageVector = Icons.Default.Add, contentDescription = "Connect Peer", modifier = Modifier.size(18.dp))
                    }
                }
            }

            // Status footnote matching desktop bottom
            val selfAddr = state.meshStatus?.selfAddr ?: "Not connected"
            val restUrl = state.baseUrl.ifEmpty { "Not configured (tap Settings)" }
            Text(
                text = "This node: $selfAddr · Mesh REST: $restUrl",
                color = MeshMuted,
                fontSize = 10.sp,
                fontFamily = FontFamily.Monospace,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }
    }
}

@Composable
fun RightChatPane(
    state: MeshUiState,
    onSetMode: (RightPaneMode) -> Unit,
    onPromptChange: (String) -> Unit,
    onSend: () -> Unit,
    onClearResponse: () -> Unit,
    onCopyText: (String) -> Unit
) {
    val selectedId = state.selectedNodeId
    val isSelfSelected = selectedId == state.meshStatus?.selfId
    val selectedName = if (isSelfSelected) {
        state.meshStatus?.selfName?.ifEmpty { "This Laptop" } ?: "This Laptop"
    } else {
        state.meshStatus?.graph?.get(selectedId)?.name ?: selectedId ?: "Select a peer"
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MeshPanel)
    ) {
        // 1. Top Bar: Peer Avatar & Name + Mode Switcher Tabs
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 14.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Box(
                    modifier = Modifier
                        .size(34.dp)
                        .clip(CircleShape)
                        .background(Color(0xFF1E1E1E))
                        .border(1.dp, MeshLine, CircleShape),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        imageVector = Icons.Default.Person,
                        contentDescription = "Peer",
                        tint = Color(0xFFCBD5E1),
                        modifier = Modifier.size(18.dp)
                    )
                }

                Column {
                    Text(
                        text = selectedName,
                        color = MeshFg,
                        style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Bold),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                    Text(
                        text = if (isSelfSelected) "Active laptop node" else "Choose another node from the graph",
                        color = MeshMuted,
                        fontSize = 11.sp
                    )
                }
            }

            // Mode Toggle Tabs: [💬 Message]  [🤖 Ask agent]
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Surface(
                    onClick = { onSetMode(RightPaneMode.MESSAGE) },
                    shape = RoundedCornerShape(6.dp),
                    color = if (state.rightPaneMode == RightPaneMode.MESSAGE) Color(0xFF262626) else Color(0xFF161616),
                    border = CardDefaults.outlinedCardBorder().copy(
                        brush = SolidColor(if (state.rightPaneMode == RightPaneMode.MESSAGE) MeshLine else Color.Transparent)
                    )
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Outlined.ChatBubbleOutline,
                            contentDescription = null,
                            tint = if (state.rightPaneMode == RightPaneMode.MESSAGE) MeshFg else MeshMuted,
                            modifier = Modifier.size(14.dp)
                        )
                        Text(
                            text = "Message",
                            color = if (state.rightPaneMode == RightPaneMode.MESSAGE) MeshFg else MeshMuted,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.SemiBold
                        )
                    }
                }

                Surface(
                    onClick = { onSetMode(RightPaneMode.ASK_AGENT) },
                    shape = RoundedCornerShape(6.dp),
                    color = if (state.rightPaneMode == RightPaneMode.ASK_AGENT) Color(0xFF262626) else Color(0xFF161616),
                    border = CardDefaults.outlinedCardBorder().copy(
                        brush = SolidColor(if (state.rightPaneMode == RightPaneMode.ASK_AGENT) MeshLine else Color.Transparent)
                    )
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Default.SmartToy,
                            contentDescription = null,
                            tint = if (state.rightPaneMode == RightPaneMode.ASK_AGENT) MeshBlue else MeshMuted,
                            modifier = Modifier.size(14.dp)
                        )
                        Text(
                            text = "Ask agent",
                            color = if (state.rightPaneMode == RightPaneMode.ASK_AGENT) MeshFg else MeshMuted,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.SemiBold
                        )
                    }
                }
            }
        }

        HorizontalDivider(color = MeshLine)

        // 2. Middle Content Area
        Box(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
                .padding(14.dp)
        ) {
            when (state.rightPaneMode) {
                RightPaneMode.ASK_AGENT -> {
                    AgentContentView(
                        state = state,
                        onClearResponse = onClearResponse,
                        onCopy = onCopyText
                    )
                }
                RightPaneMode.MESSAGE -> {
                    MessageContentView(
                        messages = state.messages,
                        selectedNodeId = state.selectedNodeId
                    )
                }
            }
        }

        HorizontalDivider(color = MeshLine)

        // 3. Bottom Compose Bar: Input + Send + "Agent calls require a shared token"
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 14.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.Bottom,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                val placeholder = if (state.rightPaneMode == RightPaneMode.ASK_AGENT) {
                    "Ask agent on $selectedName..."
                } else {
                    "Message $selectedName..."
                }

                Box(
                    modifier = Modifier
                        .weight(1f)
                        .clip(RoundedCornerShape(12.dp))
                        .background(MeshInputBg)
                        .border(1.dp, MeshLine, RoundedCornerShape(12.dp))
                ) {
                    OutlinedTextField(
                        value = state.promptInput,
                        onValueChange = onPromptChange,
                        placeholder = { Text(placeholder, color = MeshMuted, fontSize = 13.sp) },
                        maxLines = 4,
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedTextColor = MeshFg,
                            unfocusedTextColor = MeshFg,
                            focusedBorderColor = Color.Transparent,
                            unfocusedBorderColor = Color.Transparent,
                            cursorColor = MeshBlue
                        ),
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 4.dp)
                            .testTag("prompt_input"),
                        textStyle = MaterialTheme.typography.bodyMedium
                    )
                }

                val isSending = state.isExecutingPrompt || state.isSendingMessage
                Button(
                    onClick = onSend,
                    enabled = state.promptInput.isNotBlank() && !isSending,
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (state.rightPaneMode == RightPaneMode.ASK_AGENT) MeshBlue else MeshGreen,
                        contentColor = Color.White
                    ),
                    modifier = Modifier
                        .size(46.dp)
                        .testTag("send_prompt_button"),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(0.dp)
                ) {
                    if (isSending) {
                        CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp, color = Color.White)
                    } else {
                        Icon(imageVector = Icons.AutoMirrored.Filled.Send, contentDescription = "Send", modifier = Modifier.size(18.dp))
                    }
                }
            }

            // Desktop Subtitle note
            Text(
                text = "Enter to send · Shift+Enter for a new line · Agent calls require a shared token",
                color = MeshMuted,
                fontSize = 10.sp,
                textAlign = TextAlign.Center,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 2.dp)
            )
        }
    }
}

@Composable
fun AgentContentView(
    state: MeshUiState,
    onClearResponse: () -> Unit,
    onCopy: (String) -> Unit
) {
    val scrollState = rememberLazyListState()

    if (state.lastResponse == null && state.lastError == null && !state.isExecutingPrompt) {
        // Empty State matching screenshot
        Column(
            modifier = Modifier.fillMaxSize(),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Box(
                modifier = Modifier
                    .size(52.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .background(Color(0xFF18181B))
                    .border(1.dp, MeshLine, RoundedCornerShape(12.dp)),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    imageVector = Icons.Default.Hub,
                    contentDescription = null,
                    tint = MeshMuted,
                    modifier = Modifier.size(26.dp)
                )
            }
            Spacer(modifier = Modifier.height(14.dp))
            Text(
                text = "Select a Mesh peer",
                color = MeshFg,
                style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.Bold)
            )
            Spacer(modifier = Modifier.height(6.dp))
            Text(
                text = "Choose a node in the network to message its owner or call its agent.",
                color = MeshMuted,
                fontSize = 12.sp,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(horizontal = 24.dp)
            )
        }
    } else {
        LazyColumn(
            state = scrollState,
            modifier = Modifier.fillMaxSize(),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            if (state.isExecutingPrompt) {
                item {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(10.dp),
                        colors = CardDefaults.cardColors(containerColor = Color(0xFF0F172A)),
                        border = CardDefaults.outlinedCardBorder().copy(brush = SolidColor(Color(0xFF0284C7)))
                    ) {
                        Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text(
                                    text = "Agent running in-process on laptop...",
                                    color = Color(0xFF38BDF8),
                                    style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.SemiBold)
                                )
                                Text(
                                    text = "${state.executionDurationSeconds}s",
                                    color = Color.White,
                                    fontSize = 11.sp,
                                    fontFamily = FontFamily.Monospace
                                )
                            }
                            LinearProgressIndicator(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .height(3.dp),
                                color = Color(0xFF38BDF8),
                                trackColor = Color(0xFF1E293B)
                            )
                        }
                    }
                }
            }

            if (state.lastResponse != null || state.lastError != null) {
                item {
                    val isSuccess = state.executionSuccess ?: (state.lastError == null)
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .testTag("response_card"),
                        shape = RoundedCornerShape(12.dp),
                        colors = CardDefaults.cardColors(containerColor = Color(0xFF0E0E10)),
                        border = CardDefaults.outlinedCardBorder().copy(
                            brush = SolidColor(if (isSuccess) MeshGreen else Color(0xFFEF4444))
                        )
                    ) {
                        Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                                ) {
                                    Icon(
                                        imageVector = if (isSuccess) Icons.Default.CheckCircle else Icons.Default.ErrorOutline,
                                        contentDescription = null,
                                        tint = if (isSuccess) MeshGreen else Color(0xFFEF4444),
                                        modifier = Modifier.size(16.dp)
                                    )
                                    Text(
                                        text = if (isSuccess) "Agent Response" else "Execution Error",
                                        color = if (isSuccess) MeshGreen else Color(0xFFEF4444),
                                        style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.Bold)
                                    )
                                }

                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    if (state.lastExecutionTimeMs != null) {
                                        Text(
                                            text = "${state.lastExecutionTimeMs / 1000.0}s",
                                            color = MeshMuted,
                                            fontSize = 11.sp,
                                            fontFamily = FontFamily.Monospace,
                                            modifier = Modifier.padding(end = 8.dp)
                                        )
                                    }
                                    IconButton(
                                        onClick = { onCopy(state.lastResponse ?: state.lastError ?: "") },
                                        modifier = Modifier.size(28.dp)
                                    ) {
                                        Icon(imageVector = Icons.Default.ContentCopy, contentDescription = "Copy", tint = MeshMuted, modifier = Modifier.size(14.dp))
                                    }
                                    IconButton(
                                        onClick = onClearResponse,
                                        modifier = Modifier.size(28.dp)
                                    ) {
                                        Icon(imageVector = Icons.Default.Clear, contentDescription = "Clear", tint = MeshMuted, modifier = Modifier.size(14.dp))
                                    }
                                }
                            }

                            HorizontalDivider(color = MeshLine)

                            Text(
                                text = state.lastResponse ?: state.lastError ?: "",
                                color = if (isSuccess) MeshFg else Color(0xFFFCA5A5),
                                style = MaterialTheme.typography.bodySmall.copy(
                                    fontFamily = FontFamily.Monospace,
                                    lineHeight = 18.sp
                                ),
                                modifier = Modifier.padding(top = 4.dp)
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun MessageContentView(
    messages: List<MeshMessageItem>,
    selectedNodeId: String?
) {
    if (messages.isEmpty()) {
        Column(
            modifier = Modifier.fillMaxSize(),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Text(
                text = "No messages yet. Say hello.",
                color = MeshMuted,
                fontSize = 12.sp
            )
        }
    } else {
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            items(messages) { msg ->
                val isMine = msg.to == selectedNodeId || msg.from == null
                Box(
                    modifier = Modifier.fillMaxWidth(),
                    contentAlignment = if (isMine) Alignment.CenterEnd else Alignment.CenterStart
                ) {
                    Box(
                        modifier = Modifier
                            .clip(RoundedCornerShape(12.dp))
                            .background(if (isMine) MeshBlue else Color(0xFF1C1C1C))
                            .padding(horizontal = 12.dp, vertical = 8.dp)
                    ) {
                        Text(
                            text = msg.msg,
                            color = Color.White,
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                }
            }
        }
    }
}

enum class SettingsNetworkTab {
    WIFI,
    BLUETOOTH
}

@Composable
fun SettingsDialog(
    baseUrl: String,
    bearerToken: String,
    onBaseUrlChange: (String) -> Unit,
    onBearerTokenChange: (String) -> Unit,
    onDismiss: () -> Unit,
    onTest: () -> Unit
) {
    var showToken by remember { mutableStateOf(false) }
    var networkTab by remember {
        mutableStateOf(
            if (baseUrl.contains("192.168.44.")) SettingsNetworkTab.BLUETOOTH else SettingsNetworkTab.WIFI
        )
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = Color(0xFF141414),
        shape = RoundedCornerShape(16.dp),
        title = {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Icon(
                    imageVector = Icons.Default.Settings,
                    contentDescription = null,
                    tint = MeshGreen,
                    modifier = Modifier.size(20.dp)
                )
                Text(
                    "Network & Auth Settings",
                    color = MeshFg,
                    style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold)
                )
            }
        },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(14.dp)
            ) {
                // Network Mode Tabs
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(8.dp))
                        .background(Color(0xFF0D0D0D))
                        .border(1.dp, MeshLine, RoundedCornerShape(8.dp))
                        .padding(3.dp),
                    horizontalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    Surface(
                        onClick = { networkTab = SettingsNetworkTab.WIFI },
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(6.dp),
                        color = if (networkTab == SettingsNetworkTab.WIFI) Color(0xFF262626) else Color.Transparent
                    ) {
                        Row(
                            modifier = Modifier.padding(vertical = 7.dp),
                            horizontalArrangement = Arrangement.Center,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Icon(
                                imageVector = Icons.Default.Wifi,
                                contentDescription = null,
                                tint = if (networkTab == SettingsNetworkTab.WIFI) MeshGreen else MeshMuted,
                                modifier = Modifier.size(14.dp)
                            )
                            Spacer(modifier = Modifier.width(6.dp))
                            Text(
                                text = "Wi-Fi LAN",
                                color = if (networkTab == SettingsNetworkTab.WIFI) MeshFg else MeshMuted,
                                fontSize = 12.sp,
                                fontWeight = FontWeight.SemiBold
                            )
                        }
                    }

                    Surface(
                        onClick = { networkTab = SettingsNetworkTab.BLUETOOTH },
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(6.dp),
                        color = if (networkTab == SettingsNetworkTab.BLUETOOTH) Color(0xFF1E3A8A) else Color.Transparent
                    ) {
                        Row(
                            modifier = Modifier.padding(vertical = 7.dp),
                            horizontalArrangement = Arrangement.Center,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Icon(
                                imageVector = Icons.Default.Bluetooth,
                                contentDescription = null,
                                tint = if (networkTab == SettingsNetworkTab.BLUETOOTH) Color(0xFF60A5FA) else MeshMuted,
                                modifier = Modifier.size(14.dp)
                            )
                            Spacer(modifier = Modifier.width(6.dp))
                            Text(
                                text = "Bluetooth PAN",
                                color = if (networkTab == SettingsNetworkTab.BLUETOOTH) Color(0xFFDBEAFE) else MeshMuted,
                                fontSize = 12.sp,
                                fontWeight = FontWeight.SemiBold
                            )
                        }
                    }
                }

                // Helper Card Based on Selected Tab
                if (networkTab == SettingsNetworkTab.BLUETOOTH) {
                    Card(
                        shape = RoundedCornerShape(10.dp),
                        colors = CardDefaults.cardColors(containerColor = Color(0xFF0F172A)),
                        border = CardDefaults.outlinedCardBorder().copy(brush = SolidColor(Color(0xFF1D4ED8)))
                    ) {
                        Column(
                            modifier = Modifier.padding(12.dp),
                            verticalArrangement = Arrangement.spacedBy(6.dp)
                        ) {
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(6.dp)
                            ) {
                                Icon(
                                    imageVector = Icons.Default.Bluetooth,
                                    contentDescription = null,
                                    tint = Color(0xFF38BDF8),
                                    modifier = Modifier.size(16.dp)
                                )
                                Text(
                                    text = "Bluetooth Tethering Setup",
                                    color = Color(0xFF38BDF8),
                                    style = MaterialTheme.typography.labelMedium.copy(fontWeight = FontWeight.Bold)
                                )
                            }
                            Text(
                                text = "1. Pair phone & laptop in Windows Bluetooth Settings.\n" +
                                       "2. Android: Settings > Hotspot & tethering > Bluetooth tethering (turn ON).\n" +
                                       "3. Windows: Settings > Bluetooth > Devices > phone > Connect using > Access point.\n" +
                                       "4. Tap the 192.168.44.1 preset below.",
                                color = Color(0xFFCBD5E1),
                                fontSize = 11.sp,
                                lineHeight = 16.sp
                            )
                        }
                    }

                    // Quick-Fill Presets for Bluetooth
                    Text("Quick-fill Bluetooth Presets:", color = MeshMuted, fontSize = 11.sp)
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Surface(
                            onClick = { onBaseUrlChange("http://192.168.44.1:8766") },
                            shape = RoundedCornerShape(8.dp),
                            color = Color(0xFF1E293B),
                            border = CardDefaults.outlinedCardBorder().copy(brush = SolidColor(Color(0xFF334155))),
                            modifier = Modifier.weight(1f)
                        ) {
                            Column(modifier = Modifier.padding(8.dp)) {
                                Text("Android BT Gateway", color = Color(0xFF93C5FD), fontSize = 11.sp, fontWeight = FontWeight.Bold)
                                Text("192.168.44.1:8766", color = MeshMuted, fontSize = 10.sp, fontFamily = FontFamily.Monospace)
                            }
                        }

                        Surface(
                            onClick = { onBaseUrlChange("http://192.168.44.2:8766") },
                            shape = RoundedCornerShape(8.dp),
                            color = Color(0xFF1E293B),
                            border = CardDefaults.outlinedCardBorder().copy(brush = SolidColor(Color(0xFF334155))),
                            modifier = Modifier.weight(1f)
                        ) {
                            Column(modifier = Modifier.padding(8.dp)) {
                                Text("Laptop BT Adapter", color = Color(0xFF93C5FD), fontSize = 11.sp, fontWeight = FontWeight.Bold)
                                Text("192.168.44.2:8766", color = MeshMuted, fontSize = 10.sp, fontFamily = FontFamily.Monospace)
                            }
                        }
                    }
                } else {
                    // Wi-Fi Setup Guidance Card
                    Card(
                        shape = RoundedCornerShape(10.dp),
                        colors = CardDefaults.cardColors(containerColor = Color(0xFF14241B)),
                        border = CardDefaults.outlinedCardBorder().copy(brush = SolidColor(Color(0xFF15803D)))
                    ) {
                        Column(
                            modifier = Modifier.padding(12.dp),
                            verticalArrangement = Arrangement.spacedBy(6.dp)
                        ) {
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(6.dp)
                            ) {
                                Icon(
                                    imageVector = Icons.Default.Wifi,
                                    contentDescription = null,
                                    tint = MeshGreen,
                                    modifier = Modifier.size(16.dp)
                                )
                                Text(
                                    text = "Wi-Fi LAN Connection Steps",
                                    color = Color(0xFFA7F3D0),
                                    style = MaterialTheme.typography.labelMedium.copy(fontWeight = FontWeight.Bold)
                                )
                            }
                            Text(
                                text = "1. PC: run 'ipconfig' in Command Prompt to find your Wi-Fi IPv4 address (e.g. 192.168.1.42).\n" +
                                       "2. PC: run 'allow_mesh_firewall.bat' as Administrator to allow TCP 8766.\n" +
                                       "3. PC: run 'python mesh\\server.py --port 8765' (REST API listens on 8766).\n" +
                                       "4. Both phone & PC must be on the same Wi-Fi (disable AP/Client Isolation on router).\n" +
                                       "5. Never use 'localhost' on phone—enter http://<PC-IPv4>:8766 below.",
                                color = Color(0xFFD1FAE5),
                                fontSize = 11.sp,
                                lineHeight = 16.sp
                            )
                        }
                    }

                    // Common LAN subnet helpers
                    Text("Common Subnet Templates (tap to insert):", color = MeshMuted, fontSize = 11.sp)
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Surface(
                            onClick = { onBaseUrlChange("http://192.168.1.:8766") },
                            shape = RoundedCornerShape(8.dp),
                            color = Color(0xFF1E1E1E),
                            border = CardDefaults.outlinedCardBorder().copy(brush = SolidColor(MeshLine)),
                            modifier = Modifier.weight(1f)
                        ) {
                            Column(modifier = Modifier.padding(8.dp)) {
                                Text("192.168.1.x", color = Color(0xFFA7F3D0), fontSize = 11.sp, fontWeight = FontWeight.Bold)
                                Text("http://192.168.1._:8766", color = MeshMuted, fontSize = 10.sp, fontFamily = FontFamily.Monospace)
                            }
                        }

                        Surface(
                            onClick = { onBaseUrlChange("http://192.168.0.:8766") },
                            shape = RoundedCornerShape(8.dp),
                            color = Color(0xFF1E1E1E),
                            border = CardDefaults.outlinedCardBorder().copy(brush = SolidColor(MeshLine)),
                            modifier = Modifier.weight(1f)
                        ) {
                            Column(modifier = Modifier.padding(8.dp)) {
                                Text("192.168.0.x", color = Color(0xFFA7F3D0), fontSize = 11.sp, fontWeight = FontWeight.Bold)
                                Text("http://192.168.0._:8766", color = MeshMuted, fontSize = 10.sp, fontFamily = FontFamily.Monospace)
                            }
                        }

                        Surface(
                            onClick = { onBaseUrlChange("http://10.0.0.:8766") },
                            shape = RoundedCornerShape(8.dp),
                            color = Color(0xFF1E1E1E),
                            border = CardDefaults.outlinedCardBorder().copy(brush = SolidColor(MeshLine)),
                            modifier = Modifier.weight(1f)
                        ) {
                            Column(modifier = Modifier.padding(8.dp)) {
                                Text("10.0.0.x", color = Color(0xFFA7F3D0), fontSize = 11.sp, fontWeight = FontWeight.Bold)
                                Text("http://10.0.0._:8766", color = MeshMuted, fontSize = 10.sp, fontFamily = FontFamily.Monospace)
                            }
                        }
                    }
                }

                HorizontalDivider(color = MeshLine)

                // Editable Base URL
                OutlinedTextField(
                    value = baseUrl,
                    onValueChange = onBaseUrlChange,
                    label = { Text("Mesh REST Base URL") },
                    placeholder = { Text("http://<PC-LAN-IP>:8766 (e.g. http://192.168.1.42:8766)") },
                    singleLine = true,
                    leadingIcon = {
                        Icon(
                            imageVector = if (baseUrl.contains("192.168.44.")) Icons.Default.Bluetooth else Icons.Default.Wifi,
                            contentDescription = null,
                            tint = if (baseUrl.contains("192.168.44.")) Color(0xFF38BDF8) else MeshGreen,
                            modifier = Modifier.size(18.dp)
                        )
                    },
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedTextColor = MeshFg,
                        unfocusedTextColor = MeshFg,
                        focusedBorderColor = if (baseUrl.contains("192.168.44.")) Color(0xFF38BDF8) else MeshGreen,
                        unfocusedBorderColor = MeshLine
                    ),
                    modifier = Modifier.fillMaxWidth()
                )

                // Editable Shared Token
                OutlinedTextField(
                    value = bearerToken,
                    onValueChange = onBearerTokenChange,
                    label = { Text("Shared Bearer Token (MESH_PROMPT_TOKEN)") },
                    placeholder = { Text("Matches MESH_PROMPT_TOKEN in PC .env") },
                    supportingText = {
                        Text(
                            text = "Must match MESH_PROMPT_TOKEN in your PC's .env file (distinct from MESH_AGENT_TOKEN).",
                            color = MeshMuted,
                            fontSize = 10.sp
                        )
                    },
                    singleLine = true,
                    visualTransformation = if (showToken) VisualTransformation.None else PasswordVisualTransformation(),
                    leadingIcon = {
                        Icon(
                            imageVector = Icons.Default.Key,
                            contentDescription = null,
                            tint = MeshBlue,
                            modifier = Modifier.size(18.dp)
                        )
                    },
                    trailingIcon = {
                        IconButton(onClick = { showToken = !showToken }) {
                            Icon(
                                imageVector = if (showToken) Icons.Default.VisibilityOff else Icons.Default.Visibility,
                                contentDescription = "Toggle Visibility",
                                tint = MeshMuted
                            )
                        }
                    },
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedTextColor = MeshFg,
                        unfocusedTextColor = MeshFg,
                        focusedBorderColor = MeshBlue,
                        unfocusedBorderColor = MeshLine
                    ),
                    modifier = Modifier.fillMaxWidth()
                )
            }
        },
        confirmButton = {
            Button(
                onClick = onTest,
                colors = ButtonDefaults.buttonColors(containerColor = MeshGreen, contentColor = Color.Black),
                shape = RoundedCornerShape(8.dp)
            ) {
                Text("Save & Connect", fontWeight = FontWeight.Bold)
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel", color = MeshMuted)
            }
        }
    )
}
