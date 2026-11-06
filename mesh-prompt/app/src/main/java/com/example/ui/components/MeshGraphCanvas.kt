package com.example.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Hub
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.data.model.MeshNodeInfo
import com.example.data.model.MeshStatus
import com.example.ui.theme.MeshBlue
import com.example.ui.theme.MeshGreen
import com.example.ui.theme.MeshMuted
import com.example.ui.theme.MeshNodeSelfBg
import kotlin.math.cos
import kotlin.math.sin

data class NodePosition(
    val id: String,
    val name: String,
    val isSelf: Boolean,
    val isOnline: Boolean,
    val isSelected: Boolean,
    val offset: Offset
)

@Composable
fun MeshGraphCanvas(
    status: MeshStatus?,
    selectedNodeId: String?,
    onSelectNode: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    BoxWithConstraints(
        modifier = modifier
            .fillMaxSize()
            .testTag("mesh_graph_canvas"),
        contentAlignment = Alignment.TopStart
    ) {
        val density = LocalDensity.current
        val widthPx = constraints.maxWidth.toFloat()
        val heightPx = constraints.maxHeight.toFloat()

        val selfId = status?.selfId ?: "self"
        val selfName = status?.selfName?.ifEmpty { "This Laptop" } ?: "This Laptop"
        val graph = status?.graph ?: emptyMap()

        // Prepare peer ids excluding self
        val otherNodeIds = graph.keys.filter { it != selfId }.sorted()
        val totalNodes = otherNodeIds.size + 1

        val cx = widthPx / 2f
        val cy = heightPx / 2f - with(density) { 30.dp.toPx() }
        val radius = remember(widthPx, heightPx, totalNodes) {
            val minDim = minOf(widthPx, heightPx)
            (minDim / 2f - with(density) { 60.dp.toPx() }).coerceAtLeast(with(density) { 60.dp.toPx() })
        }

        // Calculate positions
        val positions = mutableListOf<NodePosition>()
        // Self node center
        positions.add(
            NodePosition(
                id = selfId,
                name = selfName,
                isSelf = true,
                isOnline = true,
                isSelected = selectedNodeId == selfId,
                offset = Offset(cx, cy)
            )
        )

        // Radial distribution for other peers
        otherNodeIds.forEachIndexed { index, peerId ->
            val angle = (2.0 * Math.PI * index / otherNodeIds.size) - (Math.PI / 2.0)
            val px = cx + (radius * cos(angle)).toFloat()
            val py = cy + (radius * sin(angle)).toFloat()
            val info = graph[peerId]
            val peerName = info?.name?.ifEmpty { peerId.take(8) } ?: peerId.take(8)
            positions.add(
                NodePosition(
                    id = peerId,
                    name = peerName,
                    isSelf = false,
                    isOnline = true,
                    isSelected = selectedNodeId == peerId,
                    offset = Offset(px, py)
                )
            )
        }

        // 1. Draw connections lines on Canvas
        Canvas(modifier = Modifier.fillMaxSize()) {
            val drawnEdges = mutableSetOf<String>()
            for (p1 in positions) {
                val neighbors = graph[p1.id]?.neighbors ?: emptyList()
                for (nId in neighbors) {
                    val p2 = positions.find { it.id == nId } ?: continue
                    val edgeKey = if (p1.id < p2.id) "${p1.id}-${p2.id}" else "${p2.id}-${p1.id}"
                    if (edgeKey in drawnEdges) continue
                    drawnEdges.add(edgeKey)

                    drawLine(
                        color = Color(0xFF333333),
                        start = p1.offset,
                        end = p2.offset,
                        strokeWidth = 2.dp.toPx(),
                        cap = StrokeCap.Round
                    )
                }
            }
        }

        // 2. Render each Node as an interactive badge
        val nodeSizeDp = 84.dp
        val nodeSizePx = with(density) { nodeSizeDp.toPx() }

        positions.forEach { pos ->
            val left = pos.offset.x - (nodeSizePx / 2f)
            val top = pos.offset.y - (nodeSizePx / 2f)

            Box(
                modifier = Modifier
                    .offset { IntOffset(left.toInt(), top.toInt()) }
                    .size(nodeSizeDp)
                    .clip(CircleShape)
                    .background(if (pos.isSelf) MeshNodeSelfBg else Color(0xFF141414))
                    .border(
                        width = if (pos.isSelected) 3.5.dp else 2.dp,
                        color = when {
                            pos.isSelected -> MeshBlue
                            pos.isSelf -> MeshGreen
                            pos.isOnline -> MeshGreen
                            else -> Color(0xFF4A4A4A)
                        },
                        shape = CircleShape
                    )
                    .clickable { onSelectNode(pos.id) }
                    .padding(6.dp),
                contentAlignment = Alignment.Center
            ) {
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center
                ) {
                    Icon(
                        imageVector = Icons.Default.Hub,
                        contentDescription = "Node Hub",
                        tint = if (pos.isSelf) MeshGreen else Color(0xFFCBD5E1),
                        modifier = Modifier.size(18.dp)
                    )
                    Text(
                        text = pos.name,
                        color = Color(0xFFF1F5F9),
                        style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Bold, fontSize = 11.sp),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                    Text(
                        text = if (pos.isSelf) "this laptop" else pos.id.take(6),
                        color = if (pos.isSelf) Color(0xFF6EE7B7) else MeshMuted,
                        fontSize = 9.sp,
                        maxLines = 1
                    )
                }
            }
        }

        // 3. Empty state notice when 0 other peers
        if (otherNodeIds.isEmpty()) {
            Column(
                modifier = Modifier
                    .align(Alignment.Center)
                    .offset(y = 70.dp)
                    .padding(horizontal = 24.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(
                    text = "Waiting for other nodes to join this laptop",
                    style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.SemiBold),
                    color = Color(0xFFE2E8F0),
                    textAlign = TextAlign.Center
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "Connect this Mesh node to another laptop on your network.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MeshMuted,
                    textAlign = TextAlign.Center
                )
            }
        }
    }
}
