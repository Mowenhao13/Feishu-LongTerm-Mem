from src.core.pipeline_options import PipelineOptions


def test_pipeline_options_defaults_enable_all_components():
    options = PipelineOptions()

    assert options.enable_memory_extraction
    assert options.inject_entity_context
    assert options.inject_project_context
    assert options.enable_neo4j_history
    assert options.enable_embedding_dedup
    assert options.enable_llm_dedup


def test_pipeline_options_reports_exactly_changed_fields():
    full = PipelineOptions()
    variant = PipelineOptions(inject_entity_context=False)

    assert variant.changed_fields_from(full) == {"inject_entity_context"}
    assert full.changed_fields_from(variant) == {"inject_entity_context"}
