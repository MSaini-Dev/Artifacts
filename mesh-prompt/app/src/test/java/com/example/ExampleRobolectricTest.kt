package com.example

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.example.data.network.MeshApiClient
import com.example.data.storage.MeshPreferences
import com.example.ui.MeshUiState
import com.example.ui.NetworkInterfaceType
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.net.ConnectException
import java.net.NoRouteToHostException
import java.net.SocketTimeoutException
import java.net.UnknownHostException

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36])
class ExampleRobolectricTest {

    @Test
    fun `read string from context`() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val appName = context.getString(R.string.app_name)
        assertEquals("Mesh Prompt", appName)
    }

    @Test
    fun `url normalizer adds http scheme and trims trailing slashes`() {
        val client = MeshApiClient()
        assertEquals("http://192.168.1.42:8766", client.normalizeUrl("192.168.1.42:8766"))
        assertEquals("http://192.168.1.42:8766", client.normalizeUrl("http://192.168.1.42:8766/"))
        assertEquals("https://laptop.local:8766", client.normalizeUrl("https://laptop.local:8766///"))
    }

    @Test
    fun `validateUrl rejects empty, localhost, and 127_0_0_1 with actionable advice`() {
        val client = MeshApiClient()
        val emptyErr = client.validateUrl("")
        assertNotNull(emptyErr)
        assertTrue(emptyErr!!.contains("Please enter your PC's Mesh REST URL"))

        val localhostErr = client.validateUrl("http://localhost:8766")
        assertNotNull(localhostErr)
        assertTrue(localhostErr!!.contains("Cannot use 'localhost'"))
        assertTrue(localhostErr.contains("ipconfig"))

        val loopbackErr = client.validateUrl("http://127.0.0.1:8766")
        assertNotNull(loopbackErr)
        assertTrue(loopbackErr!!.contains("127.0.0.1"))
        assertTrue(loopbackErr.contains("LAN IPv4"))

        val validUrl = client.validateUrl("http://192.168.1.42:8766")
        assertNull(validUrl)
    }

    @Test
    fun `preferences defaults to empty baseUrl avoiding stale hardcoded IP`() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val prefs = MeshPreferences(context)
        // Clean any saved state for clean testing
        context.getSharedPreferences("mesh_remote_prompt_prefs", Context.MODE_PRIVATE).edit().clear().commit()
        val freshPrefs = MeshPreferences(context)
        assertEquals("", freshPrefs.baseUrl)

        freshPrefs.baseUrl = "http://192.168.1.55:8766"
        freshPrefs.bearerToken = "test_mesh_token_123"

        assertEquals("http://192.168.1.55:8766", freshPrefs.baseUrl)
        assertEquals("test_mesh_token_123", freshPrefs.bearerToken)
    }

    @Test
    fun `classifyNetworkException provides firewall advice on SocketTimeoutException`() {
        val client = MeshApiClient()
        val err = client.classifyNetworkException(SocketTimeoutException("Connect timed out"), "http://192.168.1.42:8766")
        assertTrue(err.contains("Windows Defender Firewall"))
        assertTrue(err.contains("allow_mesh_firewall.bat"))
        assertTrue(err.contains("8766"))
    }

    @Test
    fun `classifyNetworkException provides server startup advice on ConnectException`() {
        val client = MeshApiClient()
        val err = client.classifyNetworkException(ConnectException("Connection refused"), "http://192.168.1.42:8766")
        assertTrue(err.contains("Connection refused"))
        assertTrue(err.contains("mesh\\server.py --port 8765"))
        assertTrue(err.contains("8766"))
    }

    @Test
    fun `classifyNetworkException provides subnet isolation advice on NoRouteToHostException`() {
        val client = MeshApiClient()
        val err = client.classifyNetworkException(NoRouteToHostException("No route to host"), "http://192.168.1.42:8766")
        assertTrue(err.contains("No route to host"))
        assertTrue(err.contains("AP Isolation"))
    }

    @Test
    fun `interface type correctly identifies bluetooth pan versus wifi`() {
        val btState = MeshUiState(baseUrl = "http://192.168.44.1:8766")
        assertEquals(NetworkInterfaceType.BLUETOOTH_PAN, btState.interfaceType)

        val wifiState = MeshUiState(baseUrl = "http://192.168.1.42:8766")
        assertEquals(NetworkInterfaceType.WIFI, wifiState.interfaceType)

        val localState = MeshUiState(baseUrl = "http://10.0.2.2:8766")
        assertEquals(NetworkInterfaceType.LOCALHOST, localState.interfaceType)
    }
}
