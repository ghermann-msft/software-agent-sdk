"""Test for the MCP observation list bug fix."""

import json

import mcp.types
from rich.text import Text

from openhands.sdk.llm import ImageContent, TextContent
from openhands.sdk.mcp.definition import MCPToolObservation


def test_mcp_observation_with_list_json():
    """Test that MCPToolObservation can handle JSON lists without crashing.

    This test reproduces and verifies the fix for the bug where
    the JSON renderer would crash when MCP tools returned lists.
    """
    # Create a list that would cause the original bug
    list_data = ["item1", "item2", 42, True, None]
    json_string = json.dumps(list_data)

    # Create text content with the JSON list
    text_content = TextContent(text=json_string)

    # Create MCP tool result with the list JSON
    result = mcp.types.CallToolResult(
        content=[mcp.types.TextContent(type="text", text=json_string)], is_error=False
    )

    # Create observation from the result
    observation = MCPToolObservation.from_call_tool_result("test_tool", result)

    # This should not crash (it would have crashed before the fix)
    visualization = observation.visualize

    # Verify it's a Text object
    assert isinstance(visualization, Text)

    # Verify the content contains expected elements
    text_content = str(visualization)
    assert "[List with 5 items]" in text_content
    assert "item1" in text_content
    assert "item2" in text_content
    assert "42" in text_content
    assert "True" in text_content


def test_mcp_observation_with_dict_json():
    """Test that MCPToolObservation still works with dictionary JSON."""
    # Create a dictionary (this always worked)
    dict_data = {"key1": "value1", "key2": 42, "key3": None}
    json_string = json.dumps(dict_data)

    # Create MCP tool result with the dict JSON
    result = mcp.types.CallToolResult(
        content=[mcp.types.TextContent(type="text", text=json_string)], is_error=False
    )

    # Create observation from the result
    observation = MCPToolObservation.from_call_tool_result("test_tool", result)

    # This should work as before
    visualization = observation.visualize

    # Verify it's a Text object
    assert isinstance(visualization, Text)

    # Verify the content contains expected elements
    text_content = str(visualization)
    assert "key1" in text_content
    assert "value1" in text_content
    assert "key2" in text_content
    assert "42" in text_content
    # key3 should be skipped because it's None


def test_mcp_observation_with_string_json():
    """Test that MCPToolObservation works with string JSON."""
    # Create a simple string (this would have crashed before)
    string_data = "simple string response"
    json_string = json.dumps(string_data)

    # Create MCP tool result with the string JSON
    result = mcp.types.CallToolResult(
        content=[mcp.types.TextContent(type="text", text=json_string)], is_error=False
    )

    # Create observation from the result
    observation = MCPToolObservation.from_call_tool_result("test_tool", result)

    # This should not crash
    visualization = observation.visualize

    # Verify it's a Text object
    assert isinstance(visualization, Text)

    # Verify the content contains the string
    text_content = str(visualization)
    assert "simple string response" in text_content


def test_mcp_observation_with_number_json():
    """Test that MCPToolObservation works with number JSON."""
    # Create a number (this would have crashed before)
    number_data = 42
    json_string = json.dumps(number_data)

    # Create MCP tool result with the number JSON
    result = mcp.types.CallToolResult(
        content=[mcp.types.TextContent(type="text", text=json_string)], is_error=False
    )

    # Create observation from the result
    observation = MCPToolObservation.from_call_tool_result("test_tool", result)

    # This should not crash
    visualization = observation.visualize

    # Verify it's a Text object
    assert isinstance(visualization, Text)

    # Verify the content contains the number
    text_content = str(visualization)
    assert "42" in text_content


def test_mcp_observation_with_invalid_json():
    """Test that MCPToolObservation handles invalid JSON gracefully."""
    # Create invalid JSON (this should fall back to plain text)
    invalid_json = "{ invalid json }"

    # Create MCP tool result with invalid JSON
    result = mcp.types.CallToolResult(
        content=[mcp.types.TextContent(type="text", text=invalid_json)], is_error=False
    )

    # Create observation from the result
    observation = MCPToolObservation.from_call_tool_result("test_tool", result)

    # This should not crash and should fall back to plain text
    visualization = observation.visualize

    # Verify it's a Text object
    assert isinstance(visualization, Text)

    # Verify the content contains the original text
    text_content = str(visualization)
    assert "{ invalid json }" in text_content


def test_mcp_observation_with_embedded_text_resource():
    result = mcp.types.CallToolResult(
        content=[
            mcp.types.EmbeddedResource(
                resource=mcp.types.TextResourceContents(
                    uri="https://example.com/search-result",
                    mime_type="application/json",
                    text='{"answer":"current information"}',
                )
            )
        ],
        is_error=False,
    )

    observation = MCPToolObservation.from_call_tool_result("web_search", result)

    assert observation.content == [
        TextContent(text="[Tool 'web_search' executed.]"),
        TextContent(text='{"answer":"current information"}'),
    ]


def test_mcp_observation_with_embedded_image_resource():
    result = mcp.types.CallToolResult(
        content=[
            mcp.types.EmbeddedResource(
                resource=mcp.types.BlobResourceContents(
                    uri="file:///result.png",
                    mime_type="image/png",
                    blob="aW1hZ2U=",
                )
            )
        ],
        is_error=False,
    )

    observation = MCPToolObservation.from_call_tool_result("render", result)

    assert observation.content == [
        TextContent(text="[Tool 'render' executed.]"),
        ImageContent(image_urls=["data:image/png;base64,aW1hZ2U="]),
    ]


def test_mcp_observation_with_embedded_binary_resource():
    result = mcp.types.CallToolResult(
        content=[
            mcp.types.EmbeddedResource(
                resource=mcp.types.BlobResourceContents(
                    uri="file:///result.bin",
                    mime_type="application/octet-stream",
                    blob="AAEC",
                )
            )
        ],
        is_error=False,
    )

    observation = MCPToolObservation.from_call_tool_result("download", result)

    assert observation.content == [
        TextContent(text="[Tool 'download' executed.]"),
        TextContent(
            text=json.dumps(
                {
                    "uri": "file:///result.bin",
                    "mime_type": "application/octet-stream",
                    "blob": "AAEC",
                }
            )
        ),
    ]
