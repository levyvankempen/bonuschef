"""Constants used in the dags folder."""

from dagster import EnvVar

ENVIRONMENT = EnvVar("ENVIRONMENT").get_value()
