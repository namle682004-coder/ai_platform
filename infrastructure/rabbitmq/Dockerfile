FROM rabbitmq:3.13-management

# Install the delayed message exchange plugin
# This plugin is required for retry backoff in the DCP task dispatch system
ARG DELAYED_PLUGIN_VERSION=3.13.0

RUN apt-get update && apt-get install -y curl && \
    curl -fsSL -o /opt/rabbitmq/plugins/rabbitmq_delayed_message_exchange-${DELAYED_PLUGIN_VERSION}.ez \
    https://github.com/rabbitmq/rabbitmq-delayed-message-exchange/releases/download/v${DELAYED_PLUGIN_VERSION}/rabbitmq_delayed_message_exchange-${DELAYED_PLUGIN_VERSION}.ez && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy configuration files
COPY enabled_plugins /etc/rabbitmq/enabled_plugins
COPY rabbitmq.conf /etc/rabbitmq/rabbitmq.conf

EXPOSE 5672 15672