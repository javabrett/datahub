package com.linkedin.metadata.usage.identity;

import com.datahub.authentication.Actor;
import com.datahub.authentication.ActorType;
import com.datahub.authentication.Authentication;
import com.linkedin.metadata.Constants;
import com.linkedin.metadata.usage.identity.CorpUserFlagsProvider.CorpUserFlags;
import com.linkedin.metadata.usage.instrumentation.UsageRequestState;
import io.datahubproject.metadata.context.OperationContext;
import io.datahubproject.metadata.context.RequestContext;
import io.datahubproject.metadata.context.usage.UsageActorClass;
import io.datahubproject.test.metadata.context.TestOperationContexts;
import org.testng.Assert;
import org.testng.annotations.AfterMethod;
import org.testng.annotations.BeforeMethod;
import org.testng.annotations.Test;

public class UsageActorClassResolverTest {

  private final UsageActorClassResolver defaultResolver =
      new UsageActorClassResolver(new AspectCorpUserFlagsProvider());

  @BeforeMethod
  @AfterMethod
  public void clearSessionFlags() {
    UsageRequestState.clear();
  }

  @Test
  public void testSystemActorUrn() throws Exception {
    Assert.assertEquals(
        defaultResolver.resolve(
            context(Constants.SYSTEM_ACTOR),
            request(Constants.SYSTEM_ACTOR),
            userAuth(Constants.SYSTEM_ACTOR)),
        UsageActorClass.SYSTEM);
  }

  @Test
  public void testDatahubActorIsSupport() throws Exception {
    Assert.assertEquals(
        defaultResolver.resolve(
            context(Constants.DATAHUB_ACTOR),
            request(Constants.DATAHUB_ACTOR),
            userAuth(Constants.DATAHUB_ACTOR)),
        UsageActorClass.SUPPORT);
  }

  @Test
  public void testAdminActorIsSupport() throws Exception {
    Assert.assertEquals(
        defaultResolver.resolve(
            context(Constants.ADMIN_ACTOR),
            request(Constants.ADMIN_ACTOR),
            userAuth(Constants.ADMIN_ACTOR)),
        UsageActorClass.SUPPORT);
  }

  @Test
  public void testRegularCorpUser() throws Exception {
    Assert.assertEquals(
        defaultResolver.resolve(
            context(Constants.METATDATA_TEST_ACTOR),
            request(Constants.METATDATA_TEST_ACTOR),
            userAuth(Constants.METATDATA_TEST_ACTOR)),
        UsageActorClass.REGULAR);
  }

  @Test
  public void testSupportUserCorpUserIsSupport() throws Exception {
    UsageActorClassResolver resolver =
        new UsageActorClassResolver(new FixedCorpUserFlagsProvider(false, true));
    Assert.assertEquals(
        resolver.resolve(
            context(Constants.METATDATA_TEST_ACTOR),
            request(Constants.METATDATA_TEST_ACTOR),
            userAuth(Constants.METATDATA_TEST_ACTOR)),
        UsageActorClass.SUPPORT);
  }

  @Test
  public void testSystemCorpUserIsSystem() throws Exception {
    UsageActorClassResolver resolver =
        new UsageActorClassResolver(new FixedCorpUserFlagsProvider(true, false));
    Assert.assertEquals(
        resolver.resolve(
            context(Constants.METATDATA_TEST_ACTOR),
            request(Constants.METATDATA_TEST_ACTOR),
            userAuth(Constants.METATDATA_TEST_ACTOR)),
        UsageActorClass.SYSTEM);
  }

  @Test
  public void testSessionCorpUserFlagsCachedPerRequest() throws Exception {
    CountingCorpUserFlagsProvider provider = new CountingCorpUserFlagsProvider(false, false);
    UsageActorClassResolver resolver = new UsageActorClassResolver(provider);
    OperationContext opContext = context(Constants.METATDATA_TEST_ACTOR);
    RequestContext requestContext = request(Constants.METATDATA_TEST_ACTOR);
    Authentication auth = userAuth(Constants.METATDATA_TEST_ACTOR);

    resolver.resolve(opContext, requestContext, auth);
    resolver.resolve(opContext, requestContext, auth);
    Assert.assertEquals(provider.resolveCount, 1);

    UsageRequestState.clear();
    resolver.resolve(opContext, requestContext, auth);
    Assert.assertEquals(provider.resolveCount, 2);
  }

  @Test
  public void testNullSessionActorFallsBackToRegular() throws Exception {
    OperationContext opContext = context(Constants.METATDATA_TEST_ACTOR);
    RequestContext requestContext = request(Constants.METATDATA_TEST_ACTOR);
    Authentication auth = org.mockito.Mockito.mock(Authentication.class);
    org.mockito.Mockito.when(auth.getActor()).thenReturn(null);
    Assert.assertEquals(
        defaultResolver.resolve(opContext, requestContext, auth), UsageActorClass.REGULAR);
  }

  @Test
  public void testNonSessionCorpUserLookupCachedPerRequest() throws Exception {
    CountingCorpUserFlagsProvider provider = new CountingCorpUserFlagsProvider(false, false);
    UsageActorClassResolver resolver = new UsageActorClassResolver(provider);
    String otherUser = "urn:li:corpuser:other";
    OperationContext opContext = context(Constants.METATDATA_TEST_ACTOR);
    RequestContext requestContext = request(otherUser);
    Authentication auth = userAuth(Constants.METATDATA_TEST_ACTOR);

    resolver.resolve(opContext, requestContext, auth);
    resolver.resolve(opContext, requestContext, auth);
    Assert.assertEquals(provider.resolveCount, 1);

    UsageRequestState.clear();
    resolver.resolve(opContext, requestContext, auth);
    Assert.assertEquals(provider.resolveCount, 2);
  }

  @Test
  public void testResolveCachedAcrossRecordRequestAndResponse() throws Exception {
    CountingCorpUserFlagsProvider provider = new CountingCorpUserFlagsProvider(false, false);
    UsageActorClassResolver resolver = new UsageActorClassResolver(provider);
    OperationContext opContext = context(Constants.METATDATA_TEST_ACTOR);
    RequestContext requestContext = request(Constants.METATDATA_TEST_ACTOR);
    Authentication auth = userAuth(Constants.METATDATA_TEST_ACTOR);

    resolver.resolve(opContext, requestContext, auth);
    resolver.resolve(opContext, requestContext, auth);
    Assert.assertEquals(provider.resolveCount, 1);
  }

  private static final class CountingCorpUserFlagsProvider implements CorpUserFlagsProvider {
    private final CorpUserFlags flags;
    private int resolveCount;

    private CountingCorpUserFlagsProvider(boolean system, boolean supportUser) {
      this.flags = new CorpUserFlags(system, supportUser);
    }

    @Override
    public boolean isSystemCorpUser(String corpUserUrn) {
      return flags.system();
    }

    @Override
    public boolean isSupportUser(String corpUserUrn) {
      return flags.supportUser();
    }

    @Override
    public CorpUserFlags resolveWithContext(OperationContext opContext, String corpUserUrn) {
      resolveCount++;
      return flags;
    }
  }

  private static final class FixedCorpUserFlagsProvider implements CorpUserFlagsProvider {
    private final CorpUserFlags flags;

    private FixedCorpUserFlagsProvider(boolean system, boolean supportUser) {
      this.flags = new CorpUserFlags(system, supportUser);
    }

    @Override
    public boolean isSystemCorpUser(String corpUserUrn) {
      return flags.system();
    }

    @Override
    public boolean isSupportUser(String corpUserUrn) {
      return flags.supportUser();
    }

    @Override
    public CorpUserFlags resolveWithContext(OperationContext opContext, String corpUserUrn) {
      return flags;
    }
  }

  private static OperationContext context(String actorUrn) throws Exception {
    return TestOperationContexts.systemContextNoValidate().toBuilder()
        .requestContext(request(actorUrn))
        .build(userAuth(actorUrn), true);
  }

  private static RequestContext request(String actorUrn) {
    return RequestContext.builder()
        .actorUrn(actorUrn)
        .sourceIP("127.0.0.1")
        .requestAPI(RequestContext.RequestAPI.OPENAPI)
        .requestID("test")
        .usageIdentity(actorUrn)
        .build();
  }

  private static Authentication userAuth(String actorUrn) {
    String actorId =
        actorUrn.startsWith("urn:li:corpuser:")
            ? actorUrn.substring("urn:li:corpuser:".length())
            : actorUrn;
    return new Authentication(new Actor(ActorType.USER, actorId), "Basic test");
  }
}
