# Azure Menu Worker Setup

The FastAPI deployment sends menu jobs with a send-only Service Bus credential. The Azure Function consumes jobs through its managed identity, runs OCR and LangChain normalization, stores results in Supabase, and indexes Azure AI Search.

## Create Infrastructure

Choose globally unique lowercase values before running these commands:

```bash
export AZURE_LOCATION=eastus
export AZURE_RESOURCE_GROUP=allernav-rg
export SERVICE_BUS_NAMESPACE=allernav-menu-unique
export MENU_QUEUE=menu-refresh
export FUNCTION_STORAGE=allernavworkerunique
export FUNCTION_APP=allernav-menu-worker-unique

az login
az group create --name "$AZURE_RESOURCE_GROUP" --location "$AZURE_LOCATION"

az servicebus namespace create \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "$SERVICE_BUS_NAMESPACE" \
  --location "$AZURE_LOCATION" \
  --sku Standard

az servicebus queue create \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --namespace-name "$SERVICE_BUS_NAMESPACE" \
  --name "$MENU_QUEUE" \
  --max-delivery-count 3 \
  --lock-duration PT5M

az servicebus queue authorization-rule create \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --namespace-name "$SERVICE_BUS_NAMESPACE" \
  --queue-name "$MENU_QUEUE" \
  --name allernav-api-send \
  --rights Send

az storage account create \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "$FUNCTION_STORAGE" \
  --location "$AZURE_LOCATION" \
  --sku Standard_LRS

az functionapp create \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "$FUNCTION_APP" \
  --storage-account "$FUNCTION_STORAGE" \
  --consumption-plan-location "$AZURE_LOCATION" \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --os-type Linux

az functionapp identity assign \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "$FUNCTION_APP"
```

Grant the Function permission to receive queue messages:

```bash
export FUNCTION_PRINCIPAL_ID=$(az functionapp identity show \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "$FUNCTION_APP" \
  --query principalId -o tsv)

export SERVICE_BUS_ID=$(az servicebus namespace show \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "$SERVICE_BUS_NAMESPACE" \
  --query id -o tsv)

az role assignment create \
  --assignee-object-id "$FUNCTION_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Azure Service Bus Data Receiver" \
  --scope "$SERVICE_BUS_ID"
```

## Configure Deployments

Get the send-only value for the `allernav-api` Vercel project:

```bash
az servicebus queue authorization-rule keys list \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --namespace-name "$SERVICE_BUS_NAMESPACE" \
  --queue-name "$MENU_QUEUE" \
  --name allernav-api-send \
  --query primaryConnectionString -o tsv
```

Store that output as `AZURE_SERVICE_BUS_SEND_CONNECTION_STRING` in `allernav-api`. Also set `AZURE_SERVICE_BUS_MENU_QUEUE=menu-refresh`.

Configure the Function. Replace placeholder values without committing secrets:

```bash
az functionapp config appsettings set \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "$FUNCTION_APP" \
  --settings \
    "AZURE_SERVICE_BUS_WORKER__fullyQualifiedNamespace=${SERVICE_BUS_NAMESPACE}.servicebus.windows.net" \
    "AZURE_SERVICE_BUS_MENU_QUEUE=${MENU_QUEUE}" \
    "SUPABASE_URL=$SUPABASE_URL" \
    "SUPABASE_SERVICE_ROLE_KEY=$SUPABASE_SERVICE_ROLE_KEY" \
    "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=$AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT" \
    "AZURE_DOCUMENT_INTELLIGENCE_KEY=$AZURE_DOCUMENT_INTELLIGENCE_KEY" \
    "AZURE_SEARCH_ENDPOINT=$AZURE_SEARCH_ENDPOINT" \
    "AZURE_SEARCH_API_KEY=$AZURE_SEARCH_API_KEY" \
    "AZURE_SEARCH_INDEX_NAME=$AZURE_SEARCH_INDEX_NAME" \
    "AZURE_OPENAI_ENDPOINT=$AZURE_OPENAI_ENDPOINT" \
    "AZURE_OPENAI_API_KEY=$AZURE_OPENAI_API_KEY" \
    "AZURE_OPENAI_CHAT_DEPLOYMENT=$AZURE_OPENAI_CHAT_DEPLOYMENT" \
    "AZURE_OPENAI_CHAT_API_VERSION=$AZURE_OPENAI_CHAT_API_VERSION"
```

Deploy from the shared Python application directory:

```bash
cd apps/api
python3 -m pip install -r requirements.txt
func azure functionapp publish "$FUNCTION_APP" --python
```

## Verify

```bash
curl -X POST \
  "https://allernav-api.vercel.app/api/places/forever-thai/menu-refresh" \
  --get \
  --data-urlencode "restaurant_name=Forever Thai" \
  --data-urlencode "website_url=https://www.foreverthaibushwick.com/menu"

curl "https://allernav-api.vercel.app/api/menu-refresh-jobs/JOB_ID"
curl "https://allernav-api.vercel.app/api/places/forever-thai/menu"
```
